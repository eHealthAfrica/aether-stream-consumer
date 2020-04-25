#!/usr/bin/env python

# Copyright (C) 2020 by eHealth Africa : http://www.eHealthAfrica.org
#
# See the NOTICE file distributed with this work for additional information
# regarding copyright ownership.
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from collections import OrderedDict
from dataclasses import dataclass
import enum
import json

from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Tuple,
)

from aet.jsonpath import CachedParser
from aet.resource import ResourceDefinition
from aet.logger import get_logger
from aet.kafka import KafkaConsumer, FilterConfig, MaskConfig

from app.config import get_kafka_config
from . import TransformationError
from .event import Event, KafkaMessage, TestEvent, ZeebeJob
from .zb import ZeebeConnection

LOG = get_logger('pipe')
KAFKA_CONFIG = get_kafka_config()


@dataclass
class Transition:
    input_map: Dict
    output_map: Dict = None
    pass_condition: str = None
    fail_condition: str = None

    @staticmethod
    def handle_parser_results(matches):
        if matches:
            if len(matches) > 1:
                return [i.value for i in matches]
            else:
                return [i.value for i in matches][0]

    @staticmethod
    def apply_map(map: Dict, context: Dict) -> Dict:
        _mapped = {
            k: Transition.handle_parser_results(
                CachedParser.find(v, context)) for
            k, v in map.items()
        }
        # filter out nones so key presence doesn't cause overwrite on merge
        return {k: v for k, v in _mapped.items() if v is not None}

    @staticmethod
    def apply_merge_dicts(_map: Dict, a: Dict, b: dict):
        # source from A, then update with non None contents of B
        return {
            **Transition.apply_map(
                _map, a),
            **Transition.apply_map(
                _map, b)
        }

    def prepare_input(self, input_context: Dict, transformation: ResourceDefinition) -> Dict:
        return Transition.apply_merge_dicts(
            self.input_map,                      # source
            {'transformation': transformation},  # overrides
            input_context
        )

    def prepare_output(self, result: Dict, transformation: ResourceDefinition) -> Dict:
        return Transition.apply_merge_dicts(
            self.output_map,                     # source
            {'transformation': transformation},  # overrides
            result
        )

    def check_failure(self, output: Dict):
        path, result = self.get_evaluation_condition()
        if not path:
            return
        # raises Error on failure
        self.evaluate_condition(path, result, output)

    def evaluate_condition(self, path, expected, data):
        res = Transition.handle_parser_results(
            CachedParser.find(path, data))
        if res is expected:
            return
        raw_path = path.split('.`')[0]
        checksum = Transition.handle_parser_results(
            CachedParser.find(raw_path, data))
        raise ValueError(f'Expected {checksum} at path {raw_path} to evaluate '
                         f'to {expected} from expression {path}, got {res}')

    def get_evaluation_condition(self) -> Tuple[str, bool]:
        if self.pass_condition:
            return (self.pass_condition, True)
        elif self.fail_condition:
            return (self.fail_condition, False)
        # if no conditions, this stage always passes
        return (None, True)


class PipelineConnection(enum.Enum):
    KAFKA = 1
    ZEEBE = 2


class PipelineContext(object):

    def __init__(
        self,
        event: Event = None,
        zeebe: ZeebeConnection = None,
        kafka_producer=None,  # Kafka instance (TODO add type)
        data: Dict = None  # other data to pass (consts, etc)
    ):
        self.zeebe = zeebe
        self.kafka = kafka_producer
        self.data: OrderedDict[str, Dict] = {}
        if isinstance(event, ZeebeJob):
            self.register_result('source', event.variables)
            self.register_result('headers', event.headers)
        elif isinstance(event, TestEvent):
            self.register_result('source', {
                k: event.get(k) for k in event.keys()
            })
        elif isinstance(event, KafkaMessage):
            self.register_result('source', {
                'message': event.value,
                'schema': event.schema,
                'key': event.key,
                'topic': event.topic
            })
        if data:
            for k in data.keys():
                self.register_result(k, data.get(k))
        self.source_event = event

    def register_result(self, _id, result):
        self.data[_id] = result

    def last(self) -> Dict:
        return self.data.get(list(self.data.keys())[-1])

    def to_json(self):
        return json.dumps(self.data)


@dataclass
class Stage:
    name: str
    transform_type: str
    transform_id: str
    transition: Transition
    __transform_getter: Callable = None

    def run(self, context: PipelineContext):
        try:
            return self.__get_transformation().run(context, self.transition)
        except AttributeError:
            raise TransformationError(
                f'Transformation type: "{self.transform_type}"'
                f' with id: "{self.transform_id}" not found.'
            )

    def __get_transformation(self) -> 'Transformation':  # noqa
        # having a getter here helps make testing more easy to implement.
        return self.__transform_getter(self.transform_id, self.transform_type)


class PipelinePubSub(object):
    def __init__(
        self,
        tenant: str,
        kafka_group=None,
        definition: Dict = None,
        zeebe: 'ZeebeInstance' = None  # noqa  type hint
    ):
        self.tenant = tenant
        self.kafka_group_id = kafka_group
        self.definition = definition
        self.kafka_consumer = None
        self.kafka_producer = None
        self.source_type = None
        self.zeebe: 'ZeebeInstance' = zeebe  # noqa
        self.zeebe_connection: ZeebeConnection = None

    def _make_context(self, evt: Event):
        data = {}
        if self.definition.get('const'):
            data = {'const': self.definition['const']}
        if not self.zeebe_connection:
            self.zeebe_connection = (None  # noqa
                if not self.zeebe \
                else self.zeebe.get_connection())
        return PipelineContext(
            evt,
            zeebe=self.zeebe_connection,
            kafka_producer=self.kafka_producer,
            data=data
        )

    def __message_getter(self):
        if not self.source_type:
            if 'kafka_subscription' in self.definition:
                self.source_type = PipelineConnection.KAFKA
                self.__source = self.__make_kafka_getter()

            elif 'zeebe_subscription' in self.definition:
                self.source_type = PipelineConnection.ZEEBE
                self.__source = self.__make_zeebe_getter()

        return self.__source

    def __make_kafka_getter(self):
        args = {k.lower(): v for k, v in KAFKA_CONFIG.copy().items()}
        args['group.id'] = self.kafka_group_id
        self.kafka_consumer = KafkaConsumer(**args)
        pattern = self.definition['kafka_subscription'].get('topic_pattern', '*')
        # only allow regex on the end of patterns
        if pattern.endswith('*'):
            topic = f'^{self.tenant}.{pattern}'
        else:
            topic = f'{self.tenant}.{pattern}'
        self.kafka_consumer.subscribe([topic], on_assign=self._on_kafka_assign)

        def _getter() -> Iterable[KafkaMessage]:
            messages = self.kafka_consumer.poll_and_deserialize(
                timeout=5,
                num_messages=1)
            for msg in messages:
                yield KafkaMessage(msg)
        return _getter

    def __make_zeebe_getter(self):
        workflow_id = self.definition.get('zeebe_subscription')
        if not self.zeebe_connection:
            self.zeebe_connection = (None  # noqa
                if not self.zeebe \
                else self.zeebe.get_connection())

        def _getter() -> Iterable[ZeebeJob]:
            jobs = self.zeebe_connection.job_iterator(workflow_id, self.kafka_group_id, max=50)
            c = 0
            for job in jobs:
                LOG.debug(f'got job: {json.dumps(job)}')
                c += 1
                yield job
            LOG.debug(f'No more jobs available on {workflow_id}, got {c}')
        return _getter

    def _get_events(self) -> Iterable[Event]:
        _source = self.__message_getter()
        yield from _source()

    def get(self) -> Iterable[PipelineContext]:
        evts: Iterable[Event] = self._get_events()
        for evt in evts:
            yield self._make_context(evt)

    def test(self, evt: Event) -> PipelineContext:
        return self._make_context(evt)

    # called when a subscription causes a new assignment to be given to the consumer
    def _on_kafka_assign(self, *args, **kwargs):
        assignment = args[1]
        topics = set([_part.topic for _part in assignment])
        for topic in list(topics):
            self._apply_consumer_filters(topic)

    def _apply_consumer_filters(self, topic):
        try:
            opts = self.definition['kafka_subscription']['topic_options']
            _flt = opts.get('filter_required', False)
            if _flt:
                _filter_options = {
                    'check_condition_path': opts.get('filter_field_path', ''),
                    'pass_conditions': opts.get('filter_pass_values', []),
                    'requires_approval': _flt
                }
                self.kafka_consumer.set_topic_filter_config(
                    topic,
                    FilterConfig(**_filter_options)
                )
            mask_annotation = opts.get('masking_annotation', None)
            if mask_annotation:
                _mask_options = {
                    'mask_query': mask_annotation,
                    'mask_levels': opts.get('masking_levels', []),
                    'emit_level': opts.get('masking_emit_level')
                }
                self.kafka_consumer.set_topic_mask_config(
                    topic,
                    MaskConfig(**_mask_options)
                )
        except AttributeError as aer:
            LOG.error(f'No topic options for {self._id}| {aer}')


class PipelineSet(object):
    def __init__(
        self,
        definition: Dict = None,
        getter: Callable = None,
        stages: List[Stage] = None
    ):
        if stages:
            self.stages = stages
        else:
            if not all([definition, getter]):
                raise ValueError('PipelineSet requires definition and getter')
            self.stages = self._prepare_stages(definition, getter)

    def _prepare_stages(self, definition, getter: Callable):
        return [
            Stage(
                st['name'],
                st['type'],
                st['id'],
                Transition(**st['transition']),
                getter
            )
            for st in definition.stages
        ]

    def _execute_stage(
        self,
        stage: Stage,
        context: PipelineContext,
        raise_errors=True
    ):
        try:
            # LOG.debug(f'{stage.name} Context : {json.dumps(context.data, indent=2)}')
            result = stage.run(context)
            # LOG.debug(f'{stage.name} Result : {json.dumps(result, indent=2)}')
            context.register_result(stage.name, result)
        except TransformationError as ter:
            if raise_errors:
                raise(ter)
            else:
                context.register_result(stage.name, {'error': str(ter)})

    def run(self, context: PipelineContext, raise_errors=True):
        for stage in self.stages:
            try:
                self._execute_stage(stage, context, raise_errors)
            except Exception as err:
                raise TransformationError(
                    f'On Stage "{stage.name}": {type(err).__name__}: {err}')
        return context

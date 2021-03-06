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
from dataclasses import dataclass, field
from datetime import datetime
import enum
import json
from uuid import uuid4

from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Tuple,
    Union,
)

from confluent_kafka import Producer as KafkaProducer

from aet.jsonpath import CachedParser
from aet.resource import ResourceDefinition
from aet.logger import get_logger
from aet.kafka import KafkaConsumer, FilterConfig, MaskConfig

from app.config import get_kafka_config, get_kafka_admin_config
from app.fixtures.schemas import ERROR_LOG_AVRO
from . import TransformationError
from .event import Event, KafkaMessage, TestEvent, ZeebeJob
from .kafka import TopicHelper
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
    def apply_map(obj: Union[str, List, Dict], context: Dict):
        if isinstance(obj, str) and obj.startswith('$.'):
            return Transition.handle_parser_results(CachedParser.find(obj, context))
        elif isinstance(obj, str):
            return obj
        elif isinstance(obj, list):
            return [Transition.apply_map(i, context) for i in obj]
        elif isinstance(obj, dict):
            res = {
                k: Transition.apply_map(v, context)
                for k, v in obj.items()
            }
            # filter out nones so key presence doesn't cause overwrite on merge
            return {k: v for k, v in res.items() if v is not None}

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


@dataclass
class PipelineResult:
    success: bool
    context: 'PipelineContext'
    error: str = None
    timestamp: str = field(init=False)

    def __post_init__(self):
        self.timestamp = datetime.now().isoformat()

    def for_report(self) -> Dict:
        return {k: getattr(self, k) for k in [
            'success', 'error', 'timestamp'
        ]}

    def to_json(self) -> str:
        return json.dumps(
            dict(
                **{k: getattr(self, k) for k in [
                    'success', 'error', 'timestamp'
                ]}, **{'context': self.context.data}
            ),
            indent=2)


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
        self.kafka_producer = kafka_producer
        self.event = event
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

    def to_json(self) -> str:
        return json.dumps(self.data, indent=2)


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
        self.kafka_producer = self.__get_kafka_producer()
        self.source_type = None
        self.zeebe: 'ZeebeInstance' = zeebe  # noqa
        self.zeebe_connection: ZeebeConnection = None

    def _make_context(self, evt: Event):
        data = {}
        if self.definition.get('const'):
            data = {'const': self.definition['const']}
        if not self.zeebe_connection:
            self.zeebe_connection = (
                None
                if not self.zeebe
                else self.zeebe.get_connection())
        return PipelineContext(
            evt,
            zeebe=self.zeebe_connection,
            kafka_producer=self.kafka_producer,
            data=data
        )

    def commit(self):
        if self.kafka_consumer:
            self.kafka_consumer.commit()

    def __has_kafka_setter(self) -> bool:
        if 'error_handling' in self.definition:
            return True
        return 'kafkamessage' in set(
            [stage.get('type') for stage in self.definition.get('stages', [])]
        )

    def __get_kafka_producer(self) -> KafkaProducer:
        if self.__has_kafka_setter():
            return KafkaProducer(**get_kafka_admin_config())

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
        # the usual Kafka Client Configuration
        args['group.id'] = self.kafka_group_id
        args['auto.offset.reset'] = \
            self.definition['kafka_subscription'].get('auto_offset_reset', 'earliest')
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
            self.zeebe_connection = (
                None
                if not self.zeebe
                else self.zeebe.get_connection()
            )

        def _getter() -> Iterable[ZeebeJob]:
            jobs = self.zeebe_connection.job_iterator(workflow_id, self.kafka_group_id, max=50)
            c = 0
            for job in jobs:
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
            opts = self.definition['kafka_subscription'].get('topic_options', {})
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

    # decorator
    def report(wraps):
        def fn(*args, **kwargs):
            self = args[0]
            context: PipelineContext = args[1]
            res: PipelineResult = wraps(*args, **kwargs)
            if not self.error_topic:
                return res
            msg = dict({
                'id': str(context.event.key) if context.event.key else str(uuid4()),
                'event': context.event.__class__.__name__ if context.event else None,
                'pipeline': self.pipeline
            }, **res.for_report())
            try:
                del msg['content']
            except Exception:
                pass
            if msg['success'] is False and \
                    self.definition['error_handling'].get('log_errors', True):
                self.error_topic.produce(msg, context.kafka_producer)
            if msg['success'] is True and \
                    self.definition['error_handling'].get('log_success', False):
                self.error_topic.produce(msg, context.kafka_producer)
            return res

        return fn

    def __init__(
        self,
        pipeline: str,
        tenant: str,
        definition: Dict = None,
        getter: Callable = None,
        stages: List[Stage] = None
    ):
        self.pipeline = pipeline
        self.tenant = tenant
        self.definition = definition or {}
        if stages:
            self.stages = stages
        else:
            if not all([definition, getter]):
                raise ValueError('PipelineSet requires definition and getter')
            self.stages = self._prepare_stages(definition, getter)
        # if reports to Kafka:
        self.error_topic = TopicHelper(
            json.loads(ERROR_LOG_AVRO),
            self.tenant,
            self.definition.get('error_handling').get('error_topic')
        ) if 'error_handling' in self.definition else None

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
            result = stage.run(context)
            context.register_result(stage.name, result)
        except TransformationError as ter:
            if raise_errors:
                raise(ter)
            else:
                context.register_result(stage.name, {'error': str(ter)})

    @report
    def run(self, context: PipelineContext, raise_errors=True) -> PipelineResult:
        for stage in self.stages:
            try:
                self._execute_stage(stage, context, raise_errors)
            except Exception as err:
                return PipelineResult(
                    success=False,
                    context=context,
                    error=f'On Stage "{stage.name}": {type(err).__name__}: {err}'
                )
        result = PipelineResult(
            success=True,
            context=context,
            error=None
        )
        return result

#!/usr/bin/env python

# Copyright (C) 2019 by eHealth Africa : http://www.eHealthAfrica.org
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

# import fnmatch
import json  # noqa
from time import sleep
from typing import (  # noqa
    Dict,
    List,
    Iterable,
    Tuple
)
#     Any,
#     Callable,
#     List,
#     Mapping


# from confluent_kafka import KafkaException

# Consumer SDK
from aet.exceptions import ConsumerHttpException
from aet.job import BaseJob, JobStatus
from aet.logger import get_logger
from aet.jsonpath import CachedParser
from aet.resource import BaseResource, lock

# Aether python lib
# from aether.python.avro.schema import Node

from app.config import get_consumer_config, get_kafka_config
from app.fixtures import schemas
from app.helpers import (
    PipelineContext,
    RestHelper,
    TestEvent,
    TransformationError,
    ZeebeJob
)

# from app import helpers

LOG = get_logger('artifacts')
CONSUMER_CONFIG = get_consumer_config()
KAFKA_CONFIG = get_kafka_config()


class ZeebeInstance(BaseResource):
    schema = schemas.PERMISSIVE
    jobs_path = '$.zeebe_instance'
    name = 'zeebe'
    public_actions = BaseResource.public_actions + [
        'test_connection'
    ]

    def __init__(self, tenant, definition, app=None):
        super().__init__(tenant, definition)

    @lock
    def get_session(self):
        pass

    # public method
    def test_connection(self, *args, **kwargs):
        return True  # TODO


class ZeebeSubscription(BaseResource):
    schema = schemas.PERMISSIVE
    name = 'zeebe_subscription'
    jobs_path = '$.zeebe_subscription'


class Transformation(BaseResource):
    schema = schemas.PERMISSIVE
    name = '__transformation'  # should not be directly created...
    jobs_path = None

    @staticmethod
    def handle_parser_results(matches):
        if matches:
            if len(matches) > 1:
                return [i.value for i in matches]
            else:
                return [i.value for i in matches][0]

    @staticmethod
    def apply_map(map: Dict, context: Dict) -> Dict:
        return {
            k: Transformation.handle_parser_results(
                CachedParser.find(v, context)) for
            k, v in map.items()
        }

    def _get_local_context(self, input_context: Dict) -> Dict:
        return Transformation.apply_map(
            self.definition.input_map, input_context)

    def _format_output(self, result: Dict) -> Dict:
        return Transformation.apply_map(
            self.definition.output_map, result)

    def run(self, context: PipelineContext) -> Dict:
        input_context = self._get_context_scope(context)
        try:
            local_context = self._get_local_context(input_context)
            result = self.do_work(local_context)
            output = self._format_output(result)
            self.check_failure(output)
            return output
        except Exception as err:
            raise TransformationError(err)

    def _get_context_scope(self, context: PipelineContext) -> Dict:
        return context.last()

    def do_work(self, local_context: Dict) -> Dict:
        # echo for basic testing
        return local_context

    def check_failure(self, output: Dict):
        path, result = self._get_evaluation_condition()
        if not path:
            return
        # raises Error on failure
        self._evaluate_condition(path, result, output)

    def _evaluate_condition(self, path, expected, data):
        res = Transformation.handle_parser_results(
            CachedParser.find(path, data))
        if res is expected:
            return
        raw_path = path.split('.`')[0]
        checksum = Transformation.handle_parser_results(
            CachedParser.find(raw_path, data))
        raise ValueError(f'Expected {checksum} at path {raw_path} to evaluate '
                         f'to {expected} from expression {path}, got {res}')

    def _get_evaluation_condition(self) -> Tuple[str, bool]:
        if hasattr(self.definition, 'pass_condition'):
            return (self.definition.pass_condition, True)
        elif hasattr(self.definition, 'fail_condition'):
            return (self.definition.fail_condition, False)
        # if no conditions, this stage always passes
        return (None, True)


class ZeebeComplete(Transformation):
    '''
        Check if a condition is met.
        Uses input_map to prepare output for job.
        Completes job
    '''
    name = 'zeebecomplete'

    def run(self, context: PipelineContext) -> Dict:
        input_context = context.data
        try:
            job = context.source_event
            local_context = self._get_local_context(input_context)
            # failure / pass based on global context
            self.check_failure(input_context)
            if isinstance(job, TestEvent):
                return local_context
            if not isinstance(job, ZeebeJob):
                raise TypeError('Expected source event to be ZeebeJob'
                                f' found {type(job)}.')
            job.complete(variables=local_context)
            return local_context
        except Exception as err:
            raise TransformationError(err)


class ZeebeSpawn(Transformation):
    '''

    '''
    name = 'zeebespawn'

    def run(self, context: PipelineContext) -> Dict:
        try:
            if context.zeebe is None:
                raise RuntimeError('Expected pipeline context to have '
                                   ' a ZeebeConnection, found None')
            # has all context
            input_context = context.data
            # failure / pass based on global context
            self.check_failure(input_context)
            local_context_iter = self._get_local_context(input_context)
            wf_name = self.definition.workflow_name
            for local_context in local_context_iter:
                self._handle_spawn(wf_name, local_context, context.zeebe)
            return {'success': True}
        except Exception as err:
            raise TransformationError(err)

    def _get_local_context(self, input_context: Dict) -> Iterable[Dict]:
        if self.definition.spawn_mode == 'multiple':
            path = self.definition.iterable_source
            out_path = self.definition.iterable_dest
            res = Transformation.handle_parser_results(
                CachedParser.find(path, input_context))
            for i in res:
                input_context[out_path] = i
                yield Transformation.apply_map(
                    self.definition.input_map, input_context)
            del input_context[out_path]
        else:
            yield Transformation.apply_map(
                self.definition.input_map, input_context)

    def _handle_spawn(self, wf_name, local_context, zeebe):
        res = next(zeebe.create_instance(wf_name, variables=local_context))
        LOG.info(res)
        return {'success': True}


class RestCall(Transformation):
    schema = schemas.PERMISSIVE
    name = 'restcall'
    jobs_path = None

    def _on_init(self):
        self.rest_helper = RestHelper()
        self.definition_dict = {'definition': {k: v for k, v in self.definition.items()}}

    def _get_local_context(self, input_context: Dict) -> Dict:
        _base_vars = Transformation.apply_map(
            self.definition.input_map, self.definition_dict)
        updates = {
            k: v for k, v in Transformation.apply_map(
                self.definition.input_map, input_context
            ).items() if v is not None
        }
        _base_vars.update(updates)
        return _base_vars

    def _format_output(self, result: Dict) -> Dict:
        return Transformation.apply_map(
            self.definition.output_map, result)

    def _get_context_scope(self, context: PipelineContext) -> Dict:
        return context.data

    def do_work(self, local_context: Dict) -> Dict:
        return self.rest_helper.request(**local_context)


class Pipeline(BaseResource):
    schema = schemas.PERMISSIVE
    name = 'pipeline'
    jobs_path = '$.pipeline'


class Job(BaseJob):
    name = 'job'
    _resources = [ZeebeInstance, ZeebeSubscription, Pipeline]
    schema = schemas.PERMISSIVE

    public_actions = BaseJob.public_actions + [
        'get_logs',
        'list_topics',
        'list_subscribed_topics'
    ]
    # publicly available list of topics

    def _setup(self):
        pass

    # def _job_firebase(self, config=None) -> FirebaseInstance:
    #     if config:
    #         fb: List[FirebaseInstance] = self.get_resources('firebase', config)
    #         if not fb:
    #             raise ConsumerHttpException('No Firebase associated with Job', 400)
    #         self._firebase = fb[0]
    #     return self._firebase

    def _get_messages(self, config):
        try:
            pass
        except ConsumerHttpException as cer:
            self.log.debug(f'Job not ready: {cer}')
            self.status = JobStatus.RECONFIGURE
            sleep(self.sleep_delay * 10)
            return []
        except Exception as err:
            self.log.critical(f'unhandled error: {str(err)}')
            raise err

    def _handle_new_subscriptions(self, subs):
        old_subs = list(sorted(set(self.subscribed_topics.values())))
        for sub in subs:
            pattern = sub.definition.topic_pattern
            # only allow regex on the end of patterns
            if pattern.endswith('*'):
                self.subscribed_topics[sub.id] = f'^{self.tenant}.{pattern}'
            else:
                self.subscribed_topics[sub.id] = f'{self.tenant}.{pattern}'
        new_subs = list(sorted(set(self.subscribed_topics.values())))
        _diff = list(set(old_subs).symmetric_difference(set(new_subs)))
        if _diff:
            self.log.info(f'{self.tenant} added subs to topics: {_diff}')
            self.consumer.subscribe(new_subs, on_assign=self._on_assign)

    def _handle_messages(self, config, messages):
        pass

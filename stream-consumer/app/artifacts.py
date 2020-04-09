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
    check_required,
    JSHelper,
    PipelineContext,
    RestHelper,
    Stage,
    TestEvent,
    TransformationError,
    Transition,
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

    def run(self, context: PipelineContext, transition: Transition) -> Dict:
        local_context = transition.prepare_input(context.data, self.definition)
        try:
            result = self.do_work(local_context)
            output = transition.prepare_output(result, self.definition)
            transition.check_failure(output)
            return output
        except Exception as err:
            raise TransformationError(err)

    def do_work(self, local_context: Dict) -> Dict:
        # echo for basic testing
        return local_context


class ZeebeComplete(Transformation):
    '''
        Check if a condition is met.
        Uses input_map to prepare output for job.
        Completes job
    '''
    name = 'zeebecomplete'

    def run(self, context: PipelineContext, transition: Transition) -> Dict:
        input_context = context.data
        try:
            job = context.source_event
            local_context = transition.prepare_input(context.data, self.definition)
            # failure / pass based on global context
            transition.check_failure(input_context)
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
    single_requirements = [
        'workflow',
        'mode',
        'mapping'
    ]
    multiple_requirements = [
        'workflow',
        'mode',
        'message_iterator',
        'mapping'
    ]

    def run(self, context: PipelineContext, transition: Transition) -> Dict:
        try:
            if context.zeebe is None:
                raise RuntimeError('Expected pipeline context to have '
                                   ' a ZeebeConnection, found None')
            local_context = transition.prepare_input(context.data, self.definition)
            transition.check_failure(local_context)
            for wf_name, inner_context in self._prepare_spawns(**local_context):
                self._handle_spawn(wf_name, inner_context, context.zeebe)
            return {'success': True}
        except Exception as err:
            raise TransformationError(err)

    @check_required(['single_requirements', 'multiple_requirements'])
    def _prepare_spawns(
        self,
        mode=None,
        workflow=None,
        mapping=None,
        message_iterator=None,
        message_destination=None,
        **local_context
    ) -> Iterable[Tuple[str, Dict]]:
        # returns (workflow, msg) generator
        if mode == 'single':
            yield (workflow, Transition.apply_map(
                mapping, local_context))
        elif mode == 'multiple':
            if not message_iterator:
                raise RuntimeError('Expected message_iterator in'
                                   'mode `multiple` found None')
            res = Transition.handle_parser_results(
                CachedParser.find(message_iterator, local_context))
            for msg in res:
                if message_destination:
                    yield (workflow, {
                        **{message_destination: msg},
                        **Transition.apply_map(
                            mapping, local_context)
                    })
                else:
                    yield (workflow, {
                        **msg,
                        **Transition.apply_map(
                            mapping, local_context)
                    })
        else:
            raise RuntimeError(f'Expected mode in [single, multiple], got {mode}')

    def _handle_spawn(self, wf_name, local_context, zeebe):
        next(zeebe.create_instance(wf_name, variables=local_context))
        return {'success': True}


class RestCall(Transformation):
    schema = schemas.PERMISSIVE
    name = 'restcall'
    jobs_path = None

    def _on_init(self):
        self.rest_helper = RestHelper()

    def do_work(self, local_context: Dict) -> Dict:
        return self.rest_helper.request(**local_context)


class JavascriptCall(Transformation):
    schema = schemas.PERMISSIVE
    name = 'jscall'
    jobs_path = None

    def _on_init(self):
        self.js_helper = JSHelper(self.definition)

    def do_work(self, local_context: Dict) -> Dict:
        LOG.debug(local_context)
        return self.js_helper.calculate(local_context)


class Pipeline(BaseResource):
    schema = schemas.PERMISSIVE
    name = 'pipeline'
    jobs_path = '$.pipeline'

    def _execute_stage(
        stage: Stage,
        context: PipelineContext,
        xf: Transformation,
        raise_errors=True
    ):
        try:
            result = xf.run(context, stage.transition)
            context.register_result(stage.name, result)
        except TransformationError as ter:
            if raise_errors:
                raise(ter)
            else:
                context.register_result(stage.name, str(ter))

    def __make_transform_iterator(self,):
        pass


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

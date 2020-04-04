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
# import json
from time import sleep
from typing import (
    Dict,
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
from aet.resource import BaseResource, lock

# Aether python lib
# from aether.python.avro.schema import Node

from app.config import get_consumer_config, get_kafka_config
from app.fixtures import schemas

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


class TransformationException(Exception):
    pass


class Transformation(BaseResource):
    schema = schemas.PERMISSIVE
    name = '__transformation'  # should not be directly created...
    jobs_path = None

    @staticmethod
    def apply_map(map: Dict, context: Dict) -> Dict:
        pass

    def _get_local_context(self, input_context: Dict) -> Dict:
        return Transformation.apply_map(
            self.definition.input_map, input_context)

    def _format_output(self, result: Dict) -> Dict:
        return Transformation.apply_map(
            self.definition.output_map, result)

    def run(self, input_context) -> Dict:
        try:
            local_context = self._get_local_context(input_context)
            result = self.do_work(local_context)
            output = self._format_output(result)
            self.check_failure(output)
        except Exception as err:
            raise TransformationException(err)

    def do_work(self, local_context) -> Dict:
        # echo for basic testing
        return local_context

    def check_failure(self, ouput: Dict):
        path, result = self._get_evaluation_condition()
        if not path:
            return

        # make sure only one condition is set
        # evaluate condition based on jsonpath expression
        # fails pass_condition, or triggers fail_condition
        raise ValueError('reason for failing')

    def _get_evaluation_condition(self) -> Tuple[str, bool]:
        if hasattr(self.definition, 'pass_condition'):
            return (self.definition.pass_condition, True)
        elif hasattr(self.definition, 'fail_condition'):
            return (self.definition.fail_condition, False)
        # if no conditions, this stage always passes
        return (None, True)


class JobComplete(Transformation):
    '''
        Check if a condition is met.
        Uses input_map to prepare output for job.
        Completes job
    '''
    name = 'jobcomplete'
    pass


class JobSpawn(Transformation):
    '''

    '''
    pass


class RestCallout(BaseResource):
    schema = schemas.PERMISSIVE
    name = 'restcallout'
    jobs_path = None


class Pipeline(BaseResource):
    schema = schemas.PERMISSIVE
    name = 'pipeline'
    jobs_path = '$.pipeline'


class ZeebeSink(BaseResource):
    schema = schemas.PERMISSIVE
    name = 'zeebesink'
    jobs_path = None


class ZeebeJob(BaseJob):
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

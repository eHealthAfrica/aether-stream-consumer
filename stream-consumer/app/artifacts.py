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

from functools import partial
from time import sleep
from typing import (
    List
)

from werkzeug.local import LocalProxy
# from confluent_kafka import KafkaException

# Consumer SDK
from aet.exceptions import ConsumerHttpException
from aet.job import BaseJob, JobStatus
from aet.logger import get_logger
from aet.resource import BaseResource, lock  # noqa

# App
from app import transforms
from app.config import get_consumer_config, get_kafka_config
from app.fixtures import schemas
from app.helpers import check_required, TransformationError
from app.helpers.event import (
    TestEvent,
)
from app.helpers.pipeline import (
    PipelinePubSub,
    PipelineSet,
)
from app.helpers.zb import (
    ZeebeConfig,
    ZeebeConnection
)


LOG = get_logger('artifacts')
CONSUMER_CONFIG = get_consumer_config()
KAFKA_CONFIG = get_kafka_config()


'''
! See .transforms for more Resources
'''


class ZeebeInstance(BaseResource):
    schema = schemas.PERMISSIVE
    jobs_path = None
    name = 'zeebe'
    public_actions = BaseResource.public_actions + [
        'test',
        'send_message',
        'start_workflow'
    ]

    _message_requires = {
        'message_id': 'str',
        'listener_name': 'str'
    }

    _workflow_requires = {
        'process_id': 'str'
    }

    def _on_init(self):
        d = self.definition
        self.config: ZeebeConfig = ZeebeConfig(
            url=d.url,
            client_id=d.get('client_id'),
            client_secret=d.get('client_secret'),
            audience=d.get('audience'),
            token_url=d.get('token_url')
        )

    def _on_change(self):
        self._on_init()

    def get_connection(self):
        return ZeebeConnection(self.config)

    # public method
    def test(self, *args, **kwargs):
        res = next(self.get_connection().get_topology())
        return res.brokers is not None

    @check_required('_message_requires')
    def _send_message(
        self,
        message_id,
        listener_name,
        correlationKey=None,
        ttl=600_000,  # 10 minute in mS
        variables=None,
        **kwargs  # grab any extras and ignore them
    ):
        res = next(self.get_connection().send_message(
            message_id, listener_name, correlationKey, ttl, variables
        ))
        if not (type(res).__name__ == 'PublishMessageResponse'):
            raise TransformationError(f'Message {message_id} received unknown response')
        return True

    # public!
    def send_message(self, request=None, *args, **kwargs):
        '''
        as a POST
        message_id, (required)
        listener_name, (required)
        correlationKey=None,
        ttl=600_000,  # in mS
        variables=None,  # the message
        '''
        try:
            if isinstance(request, LocalProxy):
                message = request.get_json()
            elif 'json_body' in kwargs:
                message = kwargs.get('json_body')
            else:
                raise ConsumerHttpException('Test Method expects a JSON Post', 400)
            return self._send_message(**message)
        except Exception as err:
            raise ConsumerHttpException(err, 400)

    @check_required('_workflow_requires')
    def _start_workflow(
        self,
        process_id,
        variables=None,
        version=1,
        **kwargs
    ):
        res = next(self.get_connection().create_instance(
            process_id, variables, version
        ))
        return res

    # public!
    def start_workflow(self, request=None, *args, **kwargs):
        '''
        as a POST
        process_id, (required)
        variables=None, # the Body
        version=None,
        '''
        try:
            if isinstance(request, LocalProxy):
                message = request.get_json()
            elif 'json_body' in kwargs:
                message = kwargs.get('json_body')
            else:
                raise ConsumerHttpException('Test Method expects a JSON Post', 400)
            res = self._start_workflow(**message)
            return res
        except Exception as err:
            raise ConsumerHttpException(err, 400)


class Pipeline(BaseResource):
    schema = schemas.PERMISSIVE
    name = 'pipeline'
    jobs_path = '$.pipelines'

    public_actions = BaseResource.public_actions + [
        'test'
    ]

    def _on_init(self):
        self.kafka_consumer_group = f'{self.tenant}.stream.pipeline.{self.id}'
        self.pipeline_set = PipelineSet(
            definition=self.definition,
            getter=partial(
                self.context.get, tenant=self.tenant)
        )
        self.pubsub = PipelinePubSub(
            self.tenant,
            self.kafka_consumer_group,
            self.definition,
            self._zb()
        )
        LOG.debug(f'Prepared Pipeline {self.id}')

    def _zb(self):
        if 'zeebe_instance' in self.definition:
            zb = self.context.get(
                self.definition.zeebe_instance,
                ZeebeInstance.name,
                self.tenant
            )
            return zb
        return None

    def _on_change(self):
        self._on_init()

    def run(self):
        results = []
        for ctx in self.pubsub.get():
            try:
                result = self.pipeline_set.run(ctx)
                results.append([True, result.data])
            except Exception as err:
                results.append([False, err, ctx.data])
        return results

    # public!
    def test(self, request=None, *args, **kwargs):
        try:
            if isinstance(request, LocalProxy):
                message = request.get_json()
            elif 'json_body' in kwargs:
                message = kwargs.get('json_body')
            else:
                raise ConsumerHttpException('Test Method expects a JSON Post', 400)
            context = self.pubsub.test(TestEvent(**message))
            context = self.pipeline_set.run(context)
            return context.data
        except Exception as err:
            raise ConsumerHttpException(err, 400)


class Job(BaseJob):
    name = 'job'
    _resources = [
        ZeebeInstance,
        transforms.ZeebeComplete,
        transforms.ZeebeMessage,
        transforms.ZeebeSpawn,
        transforms.RestCall,
        transforms.JavascriptCall,
        Pipeline
    ]
    schema = schemas.PERMISSIVE

    public_actions = BaseJob.public_actions

    _pipelines = None

    def _setup(self):
        self._pipelines = []

    def _job_pipelines(self, config=None) -> List[Pipeline]:
        if config:
            pl = self.get_resources('pipeline', config)
            if not pl:
                raise ConsumerHttpException('No Pipeline associated with Job', 400)
        self._pipelines = pl
        return self._pipelines

    def _get_messages(self, config):
        try:
            pls: List[Pipeline] = self._job_pipelines(config)
            for pl in pls:
                completed = 0
                ok = 0
                failed = 0
                results = pl.run()
                if results:
                    for res in results:
                        completed += 1
                        if res[0] is True:
                            ok += 1
                        else:
                            self.log.debug(res[1])
                            failed += 1

                    self.log.debug(f'Pipeline: {pl.id} did work: ok/failed/total ='
                                   f' {ok}/{failed}/{completed}')
                else:
                    self.log.debug(f'Pipeline {pl.id} is idle')
            return []
        except ConsumerHttpException as cer:
            self.log.debug(f'Job not ready: {cer}')
            self.status = JobStatus.RECONFIGURE
            sleep(self.sleep_delay * 10)
            return []
        except Exception as err:
            self.log.critical(f'unhandled error: {str(err)}')
            raise err

    def _handle_messages(self, config, messages):
        pass

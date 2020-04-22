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

# import json  # noqa
from functools import partial
from time import sleep

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


class ZeebeInstance(BaseResource):
    schema = schemas.PERMISSIVE
    jobs_path = None
    name = 'zeebe'
    public_actions = BaseResource.public_actions + [
        'test'
    ]

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


class Pipeline(BaseResource):
    schema = schemas.PERMISSIVE
    name = 'pipeline'
    jobs_path = None

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
        LOG.critical(f'Prepared Pipeline {self.id}')

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
        transforms.ZeebeSpawn,
        transforms.RestCall,
        transforms.JavascriptCall,
        Pipeline
    ]
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

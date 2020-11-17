#!/usr/bin/env python

# Copyright (C) 2020 by eHealth Africa : http://www.eHealthAfrica.org
#
# See the NOTICE file distributed with this work for additional information
# regarding copyright ownership.
#
# Licensed under the Apache License, Version 2.0 (the "License");
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

import json
from typing import (
    Dict,
    Iterable,
    Tuple
)

from confluent_kafka import Producer as KafkaProducer
from werkzeug.local import LocalProxy

from aet.exceptions import ConsumerHttpException
from aet.logger import get_logger
from aet.resource import BaseResource, Draft7Validator, ValidationError
from aet.jsonpath import CachedParser

from app.fixtures import schemas
from app.helpers import check_required, TransformationError
from app.helpers.js import JSHelper
from app.helpers.kafka import TopicHelper
from app.helpers.rest import RestHelper
from app.helpers.event import (
    TestEvent,
    ZeebeJob
)
from app.helpers.pipeline import (
    PipelineContext,
    Transition
)
from app.helpers.zb import ZeebeConnection

LOG = get_logger('transformers')


class Transformation(BaseResource):
    schema = schemas.BASIC
    name = '__transformation'  # should not be directly created...
    jobs_path = None

    public_actions = BaseResource.public_actions + [
        'test'
    ]

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

    def _on_change(self):
        self._on_init()

    # public!
    def test(self, request=None, *args, **kwargs):
        try:
            if isinstance(request, LocalProxy):
                message = request.get_json()
            elif 'json_body' in kwargs:
                message = kwargs.get('json_body')
            else:
                raise ConsumerHttpException('Test Method expects a JSON Post', 400)
            result = self.do_work(message)
            return result
        except Exception as err:
            raise ConsumerHttpException(err, 400)


class ZeebeComplete(Transformation):
    '''
        Check if a condition is met.
        Uses input_map to prepare output for job.
        Completes job
    '''
    name = 'zeebecomplete'
    schema = schemas.BASIC

    def run(self, context: PipelineContext, transition: Transition) -> Dict:
        input_context = context.data
        job = context.source_event
        try:
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
            try:
                job.fail(message=str(err))
            except Exception:
                pass
            raise TransformationError(err)


class ZeebeSpawn(Transformation):
    '''
    '''
    name = 'zeebespawn'
    schema = schemas.BASIC
    single_requirements = [
        'process_id',
        'mode',
        'mapping'
    ]
    multiple_requirements = [
        'process_id',
        'mode',
        'message_iterator',
        'mapping'
    ]
    jobs_path = None

    def run(self, context: PipelineContext, transition: Transition) -> Dict:
        try:
            if context.zeebe is None:
                raise RuntimeError('Expected pipeline context to have '
                                   ' a ZeebeConnection, found None')
            local_context = transition.prepare_input(context.data, self.definition)
            transition.check_failure(local_context)
            for spawn in self._prepare_spawns(
                    mapping=transition.output_map,
                    **local_context):
                self._handle_spawn(context.zeebe, **spawn)
            return {'success': True}
        except Exception as err:
            raise TransformationError(err)

    @check_required(['single_requirements', 'multiple_requirements'])
    def _prepare_spawns(
        self,
        mode=None,
        process_id=None,
        mapping=None,
        message_iterator=None,
        message_destination=None,
        **local_context
    ) -> Iterable[Tuple[str, Dict]]:
        # returns (process_id, msg) generator
        if mode == 'single':
            yield {
                'process_id': process_id,
                **Transition.apply_map(
                    mapping, local_context)
            }
        elif mode == 'multiple':
            if not message_iterator:
                raise RuntimeError('Expected message_iterator in'
                                   'mode `multiple` found None')
            res = Transition.handle_parser_results(
                CachedParser.find(message_iterator, local_context))
            for msg in res:
                if message_destination:
                    yield {
                        'process_id': process_id,
                        **{message_destination: msg},
                        **Transition.apply_map(
                            mapping, local_context)
                    }
                else:
                    yield {
                        'process_id': process_id,
                        **msg,
                        **Transition.apply_map(
                            mapping, local_context)
                    }
        else:
            raise RuntimeError(f'Expected mode in [single, multiple], got {mode}')

    def _handle_spawn(
        self,
        zeebe: ZeebeConnection,
        process_id: str = None,
        **local_context: Dict
    ):

        res = next(zeebe.create_instance(process_id, variables=local_context))
        return {'result': res}


class ZeebeMessage(ZeebeSpawn):
    '''
    '''
    name = 'zeebemessage'
    schema = schemas.BASIC
    s_requirements = [
        'mode',
        'message_id',
        'listener_name',
        'mapping'
    ]
    m_requirements = [
        'mode',
        'message_id',
        'listener_name',
        'message_iterator',
        'mapping'
    ]
    jobs_path = None

    @check_required(['s_requirements', 'm_requirements'])
    def _prepare_spawns(
        self,
        mode=None,
        message_id=None,
        listener_name=None,
        mapping=None,
        message_iterator=None,
        message_destination=None,
        **local_context
    ) -> Iterable[Tuple[str, Dict]]:
        # returns (workflow, msg) generator
        if mode == 'single':
            yield {
                'message_id': message_id,
                **Transition.apply_map(
                    mapping, local_context)
            }
        elif mode == 'multiple':
            if not message_iterator:
                raise RuntimeError('Expected message_iterator in'
                                   'mode `multiple` found None')
            res = Transition.handle_parser_results(
                CachedParser.find(message_iterator, local_context))
            for msg in res:
                if message_destination:
                    yield {
                        'message_id': message_id,
                        **{message_destination: msg},
                        **Transition.apply_map(
                            mapping, local_context)
                    }
                else:
                    yield {
                        'message_id': message_id,
                        **msg,
                        **Transition.apply_map(
                            mapping, local_context)
                    }
        else:
            raise RuntimeError(f'Expected mode in [single, multiple], got {mode}')

    def _handle_spawn(
        self,
        zeebe: ZeebeConnection,
        message_id: str = None,     # not really
        listener_name: str = None,  # optional, but enforced by decorator
        correlationKey: str = None,
        ttl: int = None,  # 10 minute in mS
        **local_context: Dict
    ):
        # Doesn't return anything useful
        res = next(zeebe.send_message(
            listener_name, message_id, correlationKey, ttl, variables=local_context)
        )
        if not (type(res).__name__ == 'PublishMessageResponse'):
            raise TransformationError(f'Message {message_id} received unknown response')
        return {'result': True}


class KafkaMessage(Transformation):
    name = 'kafkamessage'
    schema = schemas.KAFKA_MESSAGE
    jobs_path = None

    @classmethod
    def _validate(cls, definition, *args, **kwargs) -> bool:
        # subclassing a Resource a second time breaks some of the class methods, re-implement
        return cls._validate_pretty(definition, *args, **kwargs).get('valid')

    @classmethod
    def _validate_pretty(cls, definition, *args, **kwargs):
        '''
        Return a lengthy validations.
        {'valid': True} on success
        {'valid': False, 'validation_errors': [errors...]} on failure
        '''
        if isinstance(definition, LocalProxy):
            definition = definition.get_json()
        if not cls.validator:
            cls.validator = Draft7Validator(json.loads(cls.schema))
        errors = []
        try:
            cls.validator.validate(definition)
        except ValidationError:
            errors = sorted(cls.validator.iter_errors(definition), key=str)
        try:
            TopicHelper.parse(definition['schema'])
        except Exception:
            errors.append('Invalid Avro Schema for messages')
        topic = f'''{kwargs.get('tenant', '')}.{definition['topic']}'''
        if not TopicHelper.valid_topic(topic):
            errors.append(f'Invalid topic name: {topic}')
        return {
            'valid': len(errors) < 1,
            'validation_errors': [str(e) for e in errors]
        }

    def _on_init(self):
        self.helper = TopicHelper(
            self.definition['schema'],
            self.tenant,
            self.definition['topic']
        )
        self.last_call_kafka_error = None

    def run(self, context: PipelineContext, transition: Transition) -> Dict:
        local_context = transition.prepare_input(context.data, self.definition)
        try:
            result = self.do_work(local_context, context.kafka_producer)
            output = transition.prepare_output(result, self.definition)
            transition.check_failure(output)
            return output
        except Exception as err:
            msg = f'Error sending: {err}' if not self.last_call_kafka_error else \
                f'Error sending: {self.last_call_kafka_error}'
            raise TransformationError(msg) from err
        finally:
            self.last_call_kafka_error = None

    def acknowledge(self, err=None, msg=None, _=None, **kwargs):
        if err:
            LOG.error(f'caught error from kafka broker: {err}')
            self.last_call_kafka_error = err
        else:
            LOG.debug(f'caught success from kafka broker')

    def do_work(self, local_context: Dict, kafka: KafkaProducer) -> Dict:
        # validate the message
        if not self.helper.validate(local_context):
            raise TransformationError('Message does not conform to registered schema')
        if kafka is None:  # don't use "if not kafka" evaluates to false if it's idle
            raise TransformationError('Message valid, but no Kafka instance in context')
        # send the message
        self.helper.produce(local_context, kafka, self.acknowledge)
        # trigger producer flush to get errors, slower but that's ok
        kafka.flush()


class RestCall(Transformation):
    name = 'restcall'
    schema = schemas.BASIC
    jobs_path = None

    def _on_init(self):
        self.rest_helper = RestHelper()

    def do_work(self, local_context: Dict) -> Dict:
        return self.rest_helper.request(**local_context)


class JavascriptCall(Transformation):
    schema = schemas.JS_CALL
    name = 'jscall'
    jobs_path = None

    def _on_init(self):
        self.js_helper = JSHelper(self.definition)

    def do_work(self, local_context: Dict) -> Dict:
        return self.js_helper.calculate(local_context)

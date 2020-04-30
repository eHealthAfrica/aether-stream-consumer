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

from typing import (
    Dict,
    Iterable,
    Tuple
)

from werkzeug.local import LocalProxy

from aet.exceptions import ConsumerHttpException
from aet.logger import get_logger
from aet.resource import BaseResource
from aet.jsonpath import CachedParser

from app.fixtures import schemas
from app.helpers import check_required, TransformationError
from app.helpers.js import JSHelper
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
    schema = schemas.BASIC
    name = 'zeebecomplete'

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
        return self.js_helper.calculate(local_context)

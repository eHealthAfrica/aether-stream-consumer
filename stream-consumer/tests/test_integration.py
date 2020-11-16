#!/usr/bin/env python

# Copyright (C) 2018 by eHealth Africa : http://www.eHealthAfrica.org
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

import pytest
from time import sleep
from uuid import uuid4

from requests.exceptions import HTTPError

from app import transforms
from app.helpers import TransformationError
from app.helpers.pipeline import PipelineContext, Transition
from app.helpers.event import TestEvent
from app.helpers.zb import ZeebeError
from app.fixtures import examples

from .import LOG, TENANT, URL

from . import *  # noqa


@pytest.mark.integration
def test__broker_connect(zeebe_connection):
    res = next(zeebe_connection.get_topology())
    assert(res.brokers is not None)


# Only works against a Zeebe that uses credentials, which we can't easily do locally.

# @pytest.mark.integration
# def test__broker_bad_credentials(bad_zeebe_config):
#     conn = ZeebeConnection(bad_zeebe_config)
#     res = next(conn.get_topology())
# throws a HTTPError (401)


@pytest.mark.integration
def test__broker_send_message(zeebe_connection):
    msg = {
        'message_id': str(uuid4()),
        'listener_name': 'test-listener',
        'variables': {'something': 'meaningful'}
    }
    res = next(zeebe_connection.send_message(**msg))
    assert(type(res).__name__ == 'PublishMessageResponse')

    with pytest.raises(ZeebeError) as zer:
        next(zeebe_connection.send_message(**msg))
        # have to get actual exception from pytest catcher, not zer directly
        assert(zer.exception.code == 'StatusCode.ALREADY_EXISTS')


@pytest.mark.integration
def test__deploy_workflow(zeebe_connection, bpmn_echo, bpmn_sort):
    res = next(zeebe_connection.deploy_workflow('echo-flow', bpmn_echo))
    assert(res.workflows is not None)
    res = next(zeebe_connection.deploy_workflow('sort-flow', bpmn_sort))
    assert(res.workflows is not None)


@pytest.mark.integration
def test__start(StreamConsumer):
    pass


@pytest.mark.integration
def test__zb_connection(
    loaded_instance_manager
):
    zb = loaded_instance_manager.get('default', 'zeebe', TENANT)
    assert(zb.test() is True)


@pytest.mark.parametrize('ep,artifact', [
    ('zeebe', examples.ZEEBE_INSTANCE),
    ('jscall', examples.XF_JS_ADDER),
    ('jscall', examples.XF_JS_TYPED_ADDER),
    ('jscall', examples.XF_JS_CSV_PARSER),
    ('pipeline', examples.PIPELINE_SIMPLE)
])
@pytest.mark.integration
def test__api_add_resources(StreamConsumer, RequestClientT1, ep, artifact):
    doc_id = artifact.get("id")
    res = RequestClientT1.post(f'{URL}/{ep}/add', json=artifact)
    assert(res.json() is True)
    res = RequestClientT1.get(f'{URL}/{ep}/list')
    assert(doc_id in res.json())
    res = RequestClientT1.get(f'{URL}/{ep}/get?id={doc_id}')
    assert(doc_id == res.json()['id'])


@pytest.mark.parametrize('ep,id,artifact,result_field,result,error', [
    ('zeebe/test', 'default', {},None, True, None),
    ('zeebe/send_message', 'default', {  # missing fields
        'missing': 'id'
    }, None, None, 400),
    ('zeebe/send_message', 'default', {
        'message_id': 'a_message',
        'listener_name': 'a_listener',
    }, None, True, None),
    ('zeebe/send_message', 'default', {  # duplicate messages rejected
        'message_id': 'a_message',
        'listener_name': 'a_listener',
    }, None, None, 400),
    ('zeebe/start_workflow', 'default', {
        'process_id': 'echo-flow',
        'variables': {}
    }, 'bpmnProcessId', 'echo-flow', None),
    ('zeebe/start_workflow', 'default', {
        'process_id': 'echo-flow'
    }, 'bpmnProcessId', 'echo-flow', None),
    ('zeebe/start_workflow', 'default', {  # unknown version
        'process_id': 'echo-flow',
        'version': 0,
        'variables': {}
    }, None, None, 400),
    ('zeebe/start_workflow', 'default', {  # unknown wf
        'process_id': 'unknown',
        'variables': {}
    }, None, None, 400),
])
@pytest.mark.integration
def test__api_zeebe_calls(StreamConsumer, RequestClientT1, ep, id, artifact, result_field, result, error):  # noqa
    res = RequestClientT1.post(f'{URL}/{ep}?id={id}', json=artifact)
    if not error:
        LOG.debug(res.text)
        res.raise_for_status()
        body = res.json()
        if not result_field:
            assert(body == result)
        else:
            assert(body[result_field] == result)
    else:
        with pytest.raises(HTTPError):
            res.raise_for_status()
        LOG.debug(res.text)
        assert(res.status_code == error)


@pytest.mark.parametrize('_id,body,result_field,result_value,error', [
    ('adder', {'a': 1, 'b': 2}, 'result', 3, None),
    ('strictadder', {'a': 1, 'b': '2'}, 'result', 3, 400),
])
@pytest.mark.integration
def test__js_xf_test(
    StreamConsumer,
    RequestClientT1,
    _id,
    body,
    result_field,
    result_value,
    error
):
    res = RequestClientT1.post(f'{URL}/jscall/test?id={_id}', json=body)
    if not error:
        res.raise_for_status()
        body = res.json()
        assert(body.get(result_field) == result_value)
    else:
        with pytest.raises(HTTPError):
            res.raise_for_status()
        assert(res.status_code == error)


@pytest.mark.integration
def test__pipeline_wait_for_resource_init(
    StreamConsumer,
    RequestClientT1
):
    sleep(3)


@pytest.mark.parametrize('_id,body,result_field,result_value,error', [
    ('add_something', {'value': 1}, 'success', True, None),
    ('add_something', {'value': "1"}, 'success', False, 400)
])
@pytest.mark.integration
def test__pipeline_adder_test(
    StreamConsumer,
    RequestClientT1,
    _id,
    body,
    result_field,
    result_value,
    error
):
    res = RequestClientT1.post(f'{URL}/pipeline/test?id={_id}', json=body)
    if not error:
        res.raise_for_status()
        body = res.json()
        assert(body.get(result_field) == result_value)
    else:
        with pytest.raises(HTTPError):
            res.raise_for_status()
        assert(res.status_code == error)


@pytest.mark.parametrize('transition', [
    {
        'input_map': {
            'mode': '$.const.mode',
            'process_id': '$.const.process_id',
            'message_iterator': '$.const.message_iterator',
            'all_messages': '$.source.all_messages',
            'status': '$.source.status',
            'res': '$.source.res'
        },
        'output_map': {
            'res': '$.res'
        },
        'pass_condition': '$.status.`match(200, null)`'
    }
])
@pytest.mark.integration
def test__create_work(zeebe_connection, transition, loaded_instance_manager):
    _transition = Transition(**transition)
    xf = transforms.ZeebeSpawn('_id', examples.BASE_TRANSFORMATION, loaded_instance_manager)
    context = PipelineContext(
        TestEvent(),
        zeebe_connection
    )

    context.data = {
        'source': {
            'res': 0
        },
        'const': {
            'mode': 'single',
            'process_id': 'echo-flow',
        }

    }
    # single mode
    for x in range(0, 5):
        context.data['source'] = {'res': x, 'status': 200}
        ok = xf.run(context, _transition)
        LOG.debug(ok)
    with pytest.raises(TransformationError):
        context.data['source'] = {'res': -99, 'status': 500}
        ok = xf.run(context, _transition)
        LOG.debug(ok)
    # multimode

    context.data = {
        'source': {
            'status': 200,
            'all_messages': [{'res': v} for v in range(10, 15)]
        },
        'const': {
            'mode': 'multiple',
            'process_id': 'echo-flow',
            'mapping': {},
            'message_iterator': '$.all_messages',
        }
    }
    res = xf.run(context, _transition)
    LOG.debug(res)


@pytest.mark.integration
def test__do_some_work(zeebe_connection):
    jobs = zeebe_connection.job_iterator('echo-worker', 'lazyWorker', max=100)
    for job in jobs:
        try:
            job.fail()
            LOG.debug(job.variables)
        except Exception as aer:
            LOG.error(job.variables)


@pytest.mark.integration
def test__pipeline__read_kafka__make_job(
    StreamConsumer,
    loaded_instance_manager
):
    pl = loaded_instance_manager.get('kafka', 'pipeline', TENANT)
    spawned = 0
    odds = 0
    for x in range(5):
        results = pl.run()
        if results:
            res: 'PipelineResult'
            for res in results:
                assert(res.success is True), res
                body = res.context.data
                if body['two']['result']:
                    odds += 1
                spawned += 1
        else:
            LOG.debug('No work from Kafka this run...')
    evens = spawned - odds
    LOG.debug(f'Spawned {spawned} jobs in Zeebe, expecting {evens}')
    zb = loaded_instance_manager.get('zeebe', 'pipeline', TENANT)
    found = 0
    for x in range(5):
        if found >= evens:
            LOG.debug('Found all expected work items')
            assert(True)
            return
            break
        results = zb.run()
        if results:
            for res in results:
                found += 1
        else:
            LOG.debug('No work from Zeebe this run...')
    assert(False), f'only found {found} of expected {evens}'


@pytest.mark.integration
def test__pipeline__kafka_msg_and_log(instance_manager_requires_kafka):
    pass

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

from requests.exceptions import HTTPError

from . import *  # get all test assets from test/__init__.py
from app.helpers import Transition

# Test Suite contains both unit and integration tests
# Unit tests can be run on their own from the root directory
# enter the bash environment for the version of python you want to test
# for example for python 3
# `docker-compose run consumer-sdk-test bash`
# then start the unit tests with
# `pytest -m unit`
# to run integration tests / all tests run the test_all.sh script from the /tests directory.


# @pytest.mark.integration
# def test__broker_connect(zeebe_connection, bad_zeebe_config):
#     res = next(zeebe_connection.get_topology())
#     assert(res.brokers is not None)
#     bad_conn = helpers.ZeebeConnection(bad_zeebe_config)
#     with pytest.raises(requests.exceptions.HTTPError):
#         next(bad_conn.get_topology())


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
    # ('zeebe', ),
    # ('zeebecomplete', ),
    # ('zeebespawn', ),
    # ('restcall', ),
    # ('jscall', ),
    # ('pipeline', ),
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
    sleep(2)


@pytest.mark.parametrize('_id,body,result_field,result_value,error', [
    ('add_something', {'value': 1}, 'three', {'result': 4}, None),
    ('add_something', {'value': "1"}, 'three', {'result': 4}, 400)
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


@pytest.mark.integration
def test__pipeline_read_kafka_sub(
    StreamConsumer,
    loaded_instance_manager
):
    pl = loaded_instance_manager.get('kafka', 'pipeline', TENANT)
    for x in range(5):
        LOG.debug(pl.run())

# @pytest.mark.integration
# def test__deploy_workflow(zeebe_connection, bpmn_echo):
#     res = next(zeebe_connection.deploy_workflow('echo', bpmn_echo))
#     LOG.critical(res)


# @pytest.mark.parametrize('transition', [
#     {
#         'input_map': {
#             'mode': '$.const.mode',
#             'workflow': '$.const.workflow',
#             'mapping': '$.const.mapping',
#             'message_iterator': '$.const.message_iterator',
#             'all_messages': '$.source.all_messages',
#             'status': '$.source.status',
#             'res': '$.source.res'
#         },
#         'pass_condition': '$.status.`match(200, null)`'
#     }
# ])
# @pytest.mark.integration
# def test__create_work(zeebe_connection, transition, loaded_instance_manager):
#     _transition = Transition(**transition)
#     xf = artifacts.ZeebeSpawn('_id', examples.BASE_TRANSFORMATION, loaded_instance_manager)
#     context = helpers.PipelineContext(
#         helpers.TestEvent(),
#         zeebe_connection
#     )

#     context.data = {
#         'source': {
#             'res': 0
#         },
#         'const': {
#             'mode': 'single',
#             'workflow': 'flow',
#             'mapping': {
#                 'res': '$.res'
#             }
#         }

#     }
#     # single mode
#     for x in range(0, 5):
#         context.data['source'] = {'res': x, 'status': 200}
#         ok = xf.run(context, _transition)
#         LOG.debug(ok)
#     with pytest.raises(helpers.TransformationError):
#         context.data['source'] = {'res': -99, 'status': 500}
#         ok = xf.run(context, _transition)
#         LOG.debug(ok)
#     # multimode

#     context.data = {
#         'source': {
#             'status': 200,
#             'all_messages': [{'res': v} for v in range(10, 15)]
#         },
#         'const': {
#             'mode': 'multiple',
#             'workflow': 'flow',
#             'mapping': {},
#             'message_iterator': '$.all_messages',
#         }
#     }
#     res = xf.run(context, _transition)
#     LOG.debug(res)


# @pytest.mark.integration
# def test__do_some_work(zeebe_connection):
#     jobs = zeebe_connection.job_iterator('python-worker', 'lazyWorker', max=100)
#     for job in jobs:
#         try:
#             job.fail()
#             LOG.debug(job.variables)
#         except Exception as aer:
#             LOG.error(job.variables)
#             LOG.critical(aer)

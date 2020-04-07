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


@pytest.mark.integration
def test__broker_connect(zeebe_connection, bad_zeebe_config):
    res = next(zeebe_connection.get_topology())
    assert(res.brokers is not None)
    bad_conn = helpers.ZeebeConnection(bad_zeebe_config)
    with pytest.raises(requests.exceptions.HTTPError):
        next(bad_conn.get_topology())


# @pytest.mark.integration
# def test__deploy_workflow(zeebe_connection, bpmn_echo):
#     res = next(zeebe_connection.deploy_workflow('echo', bpmn_echo))
#     LOG.critical(res)


@pytest.mark.parametrize('transition', [
    {
        'input_map': {
            'mode': '$.const.mode',
            'workflow': '$.const.workflow',
            'mapping': '$.const.mapping',
            'message_iterator': '$.const.message_iterator',
            'all_messages': '$.source.all_messages'
        },
    }
])
@pytest.mark.integration
def test__create_work(zeebe_connection, transition):
    _transition = Transition(**transition)
    xf = artifacts.ZeebeSpawn('_id', examples.BASE_TRANSFORMATION)
    context = helpers.PipelineContext(
        helpers.TestEvent(),
        zeebe_connection
    )
    # single mode
    # for x in range(0, 5):
    #     context.data = {'source': {'ref': x, 'status': 200}}
    #     res = xf.run(context)
    #     LOG.debug(res)
    # with pytest.raises(helpers.TransformationError):
    #     context.data = {'source': {'ref': x, 'status': 500}}
    #     res = xf.run(context)
    # multimode
    messages = [{'res': v} for v in range(10, 15)]
    xf.definition.input_map = {'ref': '$.message'}
    xf.definition.spawn_mode = 'multiple'
    context.data = {
        'source': {
            'status': 200,
            'all_messages': messages},
        'const': examples.XF_ZEEBE_SPAWN_CONSTS
    }
    res = xf.run(context, _transition)
    LOG.debug(res)


@pytest.mark.integration
def test__do_some_work(zeebe_connection):
    jobs = zeebe_connection.job_iterator('python-worker', 'lazyWorker', max=100)
    for job in jobs:
        try:
            job.fail()
            LOG.debug(job.variables)
        except Exception as aer:
            LOG.error(job.variables)
            LOG.critical(aer)

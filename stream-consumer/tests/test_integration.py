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

# Test Suite contains both unit and integration tests
# Unit tests can be run on their own from the root directory
# enter the bash environment for the version of python you want to test
# for example for python 3
# `docker-compose run consumer-sdk-test bash`
# then start the unit tests with
# `pytest -m unit`
# to run integration tests / all tests run the test_all.sh script from the /tests directory.


@pytest.mark.integration
def test__setup_consumer(LocalConsumer):
    print(LocalConsumer)


@pytest.mark.integration
def test__two():
    assert(True)


# @pytest.mark.integration
# def test__consumer_add_firebase(LocalConsumer, RequestClientT1, RequestClientT2):
#     res = RequestClientT1.post(f'{URL}/firebase/add', json=examples.FB_INSTANCE)
#     assert(res.json() is True)
#     res = RequestClientT1.get(f'{URL}/firebase/list')
#     assert(res.json() != [])
#     res = RequestClientT2.get(f'{URL}/firebase/list')
#     assert(res.json() == [])
#     res = RequestClientT1.delete(f'{URL}/firebase/delete?id=default')
#     assert(res.json() is True)
#     res = RequestClientT1.get(f'{URL}/firebase/list')
#     assert(res.json() == [])


@pytest.mark.integration
def test__consumer_add_job(LocalConsumer, RequestClientT1):
    res = RequestClientT1.post(f'{URL}/job/add', json=examples.JOB)
    assert(res.json() is True)


@pytest.mark.integration
def test__consumer_add_subscription(LocalConsumer, RequestClientT1, cfs):
    res = RequestClientT1.post(f'{URL}/firebase/add', json=examples.FB_INSTANCE)
    assert(res.json() is True)
    res = RequestClientT1.post(f'{URL}/subscription/add', json=examples.SUBSCRIPTION)
    assert(res.json() is True)
    from time import sleep
    _path = examples.SUBSCRIPTION.get('fb_options').get('target_path').format(topic=TEST_TOPIC)
    for x in range(30):
        cfs_msg = helpers.read_cfs(cfs, _path)
        if cfs_msg:
            LOG.info(cfs_msg)
            return
        sleep(1)

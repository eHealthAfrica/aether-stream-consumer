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

from copy import copy

from . import *  # get all test assets from test/__init__.py
from app.fixtures import examples
from app import artifacts

# Test Suite contains both unit and integration tests
# Unit tests can be run on their own from the root directory
# enter the bash environment for the version of python you want to test
# for example for python 3
# `docker-compose run consumer-sdk-test bash`
# then start the unit tests with
# `pytest -m unit`
# to run integration tests / all tests run the test_all.sh script from the /tests directory.


@pytest.mark.unit
def test__Transformation_basic():
    trans = artifacts.Transformation('_id', examples.BASE_TRANSFORMATION_PASS)
    context = helpers.PipelineContext()
    context.register_result('source', {'ref': 200})
    assert(trans.run(context) == {'ref': 200})
    context.register_result('source', {'ref': 500})
    with pytest.raises(artifacts.TransformationException):
        trans.run(context)


@pytest.mark.unit
def test__xf_ZeebeComplete_basic():
    _def = dict(examples.BASE_TRANSFORMATION_PASS)
    _def['input_map'] = {'ref': '$.source.ref'}
    _def['pass_condition'] = '$.source.ref.`match(200, null)`'
    trans = artifacts.ZeebeComplete('_id', _def)
    context = helpers.PipelineContext(helpers.TestEvent())
    context.register_result('source', {'ref': 200})
    assert(trans.run(context) == {'ref': 200})
    context.register_result('source', {'ref': 500})
    with pytest.raises(artifacts.TransformationException):
        trans.run(context)


@pytest.mark.unit
def test__subscription_extended_validation():
    pass
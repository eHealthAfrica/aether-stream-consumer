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

from . import *  # get all test assets from test/__init__.py
from app.fixtures import examples
from app import artifacts
from app import helpers
from app.helpers import TransformationError

from aet.resource import ResourceDefinition

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
    with pytest.raises(helpers.TransformationError):
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
    with pytest.raises(helpers.TransformationError):
        trans.run(context)


@pytest.mark.parametrize('q,expect', [
    ('I am not a valid url! @#*@...', False),
    ('https://docker.local', False),
    ('http://localhost', False),
    ('https://google.com', True),
    ('https://google.com/imaginary/url.html', True)
])
@pytest.mark.unit
def test__xf_request_dns(q, expect):
    assert(helpers.RestHelper.resolve(q) is expect)


@pytest.mark.parametrize("config,exception,status", [
    ({
        'method': 'get',
        'url': 'https://jsonplaceholder.typicode.com/posts/1'
    }, None, 200),
    ({
        'method': 'post',
        'json_body': {'id': 'something or another'},
        'url': 'https://jsonplaceholder.typicode.com/posts'
    }, None, 201),
    ({
        'method': 'get',
        'url': 'https://exm.eha.im/dev/kernel/entities.json',
        'basic_auth': {'user': 'user', 'password': 'password'}
    }, None, 200),
    ({
        'method': 'get',
        'url': 'https://exm.eha.im/dev/kernel/entities.json'
    }, None, 302),
    ({
        'url': 'https://exm.eha.im/dev/kernel/entities.json'
    }, RuntimeError, None),
    ({
        'method': 'get',
        'url': 'http://localhost:5984'
    }, RuntimeError, None)
])
@pytest.mark.unit
def test__xf_request_methods(config, exception, status):

    def fn():
        rh = helpers.RestHelper()
        res = rh.request(**config)
        assert(res.get('status_code') == status)

    if exception:
        with pytest.raises(exception):
            fn()
    else:
        fn()


@pytest.mark.parametrize('definition', [
    {
        'id': '_id',
        'url': 'https://exm.eha.im/dev/kernel/entities.json',
        'basic_auth': {'user': 'user', 'password': 'password'},
        'input_map': {
            'url': '$.definition.url',
            'headers': '$.source.headers',
            'method': '$.source.method'
        },
        'output_map': {
            'status_code': '$.status_code'
        }
    }
])
@pytest.mark.parametrize("config,exception,status,definition_override", [
    ({
        'method': 'get',
    }, None, 302, None),
    ({
        'method': 'get',
        'basic_auth': None,
        'headers': {'X-Oauth-Unauthorized': 'status_code'}
    }, None, 403, None),
    ({
        'method': None,
        'url': 'https://exm.eha.im/dev/kernel/entities.json'
    }, TransformationError, 302, None),
    ({
        'method': 'get',
        'url': 'http://localhost:5984'
    }, TransformationError, 302, ('input_map', {
        'url': '$.source.url',
        'method': '$.source.method'
    }))
])
@pytest.mark.unit
def test__restcall_request_methods(definition, definition_override, config, exception, status):
    if definition_override:
        definition[definition_override[0]] = definition_override[1]

    def fn():
        rc = artifacts.RestCall('_id', definition)
        context = helpers.PipelineContext()
        context.register_result('source', config)
        res = rc.run(context)
        assert(res.get('status_code') == status)

    if exception:
        with pytest.raises(exception):
            fn()
    else:
        fn()


@pytest.mark.parametrize('definition', [
    ResourceDefinition({
        'entrypoint': 'f',
        'script': '''
            function adder(a, b) {
            return a + b;
        }
        function f(a, b) {
            return adder(a, b);
        }

        ''',
        'arguments': ['a', 'b']
    })
])
@pytest.mark.parametrize("config,exception,result", [
    ({
        'a': 1,
        'b': 100
    }, None, 101),
    ({
        'a': 'a',
        'b': 100
    }, TypeError, None),
])
@pytest.mark.unit
def test__xf_js_helper(definition, config, exception, result):

    def fn():
        h = helpers.JSHelper(definition)
        res = h.calculate(config)
        assert(res == result)
    if exception:
        with pytest.raises(exception):
            fn()
    else:
        fn()

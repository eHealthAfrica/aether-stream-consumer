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


@pytest.mark.unit
def test__Transformation_basic(BaseTransition):
    trans = artifacts.Transformation('_id', examples.BASE_TRANSFORMATION)
    context = helpers.PipelineContext()
    context.register_result('source', {'ref': 200})
    assert(trans.run(context, helpers.Transition(**examples.BASE_TRANSITION_PASS)) == {'ref': 200})
    context.register_result('source', {'ref': 500})
    with pytest.raises(helpers.TransformationError):
        trans.run(context, helpers.Transition(**examples.BASE_TRANSITION_PASS))


@pytest.mark.unit
def test__xf_ZeebeComplete_basic():
    transition = dict(examples.BASE_TRANSITION_PASS)
    transition['input_map'] = {'ref': '$.source.ref'}
    transition['pass_condition'] = '$.source.ref.`match(200, null)`'
    transition = helpers.Transition(**transition)

    transformation = artifacts.ZeebeComplete('_id', examples.BASE_TRANSFORMATION)
    context = helpers.PipelineContext(helpers.TestEvent())
    context.register_result('source', {'ref': 200})
    assert(transformation.run(context, transition) == {'ref': 200})
    context.register_result('source', {'ref': 500})
    with pytest.raises(helpers.TransformationError):
        transformation.run(context, transition)


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
@pytest.mark.integration
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


@pytest.mark.parametrize('transition', [
    {
        'input_map': {
            'url': '$.transformation.url',
            'headers': '$.source.headers',
            'method': '$.source.method'
        },
        'output_map': {
            'status_code': '$.status_code'
        }
    }
])
@pytest.mark.parametrize('definition', [
    {
        'id': '_id',
        'url': 'https://exm.eha.im/dev/kernel/entities.json',
        'basic_auth': {'user': 'user', 'password': 'password'}
    }
])
@pytest.mark.parametrize("config,exception,status,transition_override", [
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
    }, TransformationError, None, None),
    ({
        'method': 'get',
        'url': 'http://localhost:5984'
    }, TransformationError, None,
        ('input_map', {
            'url': '$.source.url'}))
])
@pytest.mark.integration
def test__restcall_request_methods(definition, transition_override, transition, config, exception, status):
    if transition_override:

        transition[transition_override[0]] = transition_override[1]
    transition = helpers.Transition(**transition)

    def fn():
        rc = artifacts.RestCall('_id', definition)
        context = helpers.PipelineContext()
        context.register_result('source', config)
        res = rc.run(context, transition)
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
@pytest.mark.parametrize("config,exception,result,definition_override", [
    ({
        'a': 1,
        'b': 100
    }, None, 101, None),
    ({
        'a': 'a',
        'b': 100
    }, None, 'a100', None  # without type checking weird things can happen
    ),
    ({
        'a': 'a',
        'b': 100
    }, TypeError, None,
        {'arguments': {'a': 'int', 'b': 'int'}}
    ),

])
@pytest.mark.unit
def test__xf_js_helper(definition, definition_override, config, exception, result):
    if definition_override:
        for k in definition_override.keys():
            definition[k] = definition_override[k]

    def fn():
        h = helpers.JSHelper(definition)
        res = h.calculate(config)
        assert(res == result)
    if exception:
        with pytest.raises(exception):
            fn()
    else:
        fn()


@pytest.mark.parametrize('definition', [
    ResourceDefinition({
        'entrypoint': 'f',
        'script': '''
        function f(myData) {
            const Parser = json2csv.Parser;
            const fields = ['a', 'b'];
            const opts = { fields };
            try {
              const parser = new Parser(opts);
              return parser.parse(myData);
            } catch (err) {
              console.error(err);
            }
        }

        ''',
        'arguments': ['jsonBody'],
        'libraries': ['https://cdn.jsdelivr.net/npm/json2csv@4.2.1/dist/json2csv.umd.js']
    })
])
@pytest.mark.unit
def test__xf_js_helper_remote_lib(definition):
    input = {'jsonBody': [{'a': 1, 'b': x} for x in range(1000)]}
    h = helpers.JSHelper(definition)
    res = h.calculate(input)
    import csv
    reader = list(csv.reader(res.splitlines(), quoting=csv.QUOTE_NONNUMERIC))
    assert(reader[1000][1] == 999)

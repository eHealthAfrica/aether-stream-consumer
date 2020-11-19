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

from copy import deepcopy
import json
import pytest
import responses

from . import TENANT
from . import *  # noqa
from app.fixtures import examples
from app import artifacts
from app import transforms
from app.helpers import TransformationError
from app.helpers.js import JSHelper
from app.helpers.rest import RestHelper
from app.helpers.event import TestEvent

from app.helpers.pipeline import (
    PipelineContext,
    PipelineSet,
    Stage,
    Transition
)

from aet.exceptions import ConsumerHttpException
from aet.resource import ResourceDefinition


@pytest.mark.unit
def test__TestEvent_as_dict():
    t = TestEvent(**{'a': 1})
    assert('a' in t.keys())
    assert(t.get('a') == 1)


@pytest.mark.unit
def test__Transformation_basic(BaseTransition):
    trans = transforms.Transformation('_id', examples.BASE_TRANSFORMATION, None)
    context = PipelineContext()
    context.register_result('source', {'ref': 200})
    assert(trans.run(context, Transition(**examples.BASE_TRANSITION_PASS)) == {
        'ref': 200,
        'list': [200],
        'const': 'c',
        'dict': {'f': 200}
    })
    context.register_result('source', {'ref': 500})
    with pytest.raises(TransformationError):
        trans.run(context, Transition(**examples.BASE_TRANSITION_PASS))


@pytest.mark.unit
def test__xf_ZeebeComplete_basic():
    transition = dict(examples.BASE_TRANSITION_PASS)
    transition['input_map'] = {'ref': '$.source.ref'}
    transition['pass_condition'] = '$.source.ref.`match(200, null)`'
    transition = Transition(**transition)

    transformation = transforms.ZeebeComplete('_id', examples.BASE_TRANSFORMATION, None)
    context = PipelineContext(
        TestEvent(**{'ref': 200}))
    # context.register_result('source', {'ref': 200})
    LOG.debug(json.dumps(context.data, indent=2))
    assert(transformation.run(context, transition) == {'ref': 200})
    context.register_result('source', {'ref': 500})
    with pytest.raises(TransformationError):
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
    assert(RestHelper.resolve(q) is expect)


@responses.activate
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
    url = config.get('url')
    method_str = config.get('method')
    method = responses.GET if method_str == 'get' else responses.POST
    body = Exception() if exception else None
    responses.add(method, url, body=body, status=status)

    def fn():
        rh = RestHelper()
        res = rh.request(**config)
        assert(res.get('status_code') == status)

    if exception:
        with pytest.raises(exception):
            fn()
    else:
        fn()


@responses.activate
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
@pytest.mark.unit
def test__restcall_request_methods(definition, transition_override, transition, config, exception, status):
    url = definition.get('url')
    method_str = config.get('method')
    method = responses.GET if method_str == 'get' else None
    body = Exception() if exception else '"{}"'
    responses.add(method, url, body=body, status=status)

    if transition_override:

        transition[transition_override[0]] = transition_override[1]
    transition = Transition(**transition)

    def fn():
        rc = transforms.RestCall('_id', definition, None)
        context = PipelineContext()
        context.register_result('source', config)
        res = rc.run(context, transition)
        assert(res.get('status_code') == status)

    if exception:
        with pytest.raises(exception):
            fn()
    else:
        fn()


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
def test__xf_js_helper(definition_override, config, exception, result):
    definition = ResourceDefinition(**examples.XF_JS_ADDER)
    if definition_override:
        for k in definition_override.keys():
            definition[k] = definition_override[k]

    def fn():
        h = JSHelper(definition)
        res = h.calculate(config)
        assert(res['result'] == result)
    if exception:
        with pytest.raises(exception):
            fn()
    else:
        fn()


@pytest.mark.parametrize('definition', [
    ResourceDefinition(examples.XF_JS_CSV_PARSER)
])
@pytest.mark.unit
def test__xf_js_helper_remote_lib(definition):
    input = {'jsonBody': [{'a': 1, 'b': x} for x in range(1000)]}
    h = JSHelper(definition)
    res = h.calculate(input)
    import csv
    reader = list(csv.reader(res['result'].splitlines(), quoting=csv.QUOTE_NONNUMERIC))
    assert(reader[1000][1] == 999)


@pytest.mark.parametrize('definition', [
    ResourceDefinition(examples.XF_KAFKA_MESSAGE)
])
@pytest.mark.unit
def test__xf_kafka_message_validate(definition):
    assert(transforms.KafkaMessage._validate(definition) is True)


@pytest.mark.unit
def test__stage_simple():
    transition = {
        'input_map': {'res': '$.source.res'},
        'output_map': {'res': '$.res'}
    }

    def _getter(*args, **kwargs):
        return transforms.Transformation('_id', examples.BASE_TRANSFORMATION, None)

    context = PipelineContext()
    context.register_result('source', {'res': 1})
    stage = Stage(
        'test', '__transformation', '_id', Transition(**transition), _getter)
    res = stage.run(context)
    assert(res['res'] == 1)


@pytest.mark.parametrize('_type,_id,kwargs,result_key,result_value,error', [
    ('jscall', 'sizer', {'obj': 1}, 'result', 8, None),
    ('jscall', 'sizer', {'obj': True}, 'result', 4, None),
    ('jscall', 'sizer', {'obj': 'a'}, 'result', 2, None),
    ('jscall', 'sizer', {'obj': [1, 2, 3]}, 'result', 24, None),
    ('jscall', 'sizer', {'obj': {'an': 'obj'}}, 'result', 6, None),
    ('jscall', 'isodd', {'value': 1}, 'result', True, None),
    ('jscall', 'isodd', {'value': 2}, 'result', False, None),
    ('jscall', 'adder', {'a': 1, 'b': 2}, 'result', 3, None),
    ('jscall', 'adder', {'a': 101, 'b': 2}, 'result', 103, None),
    ('jscall', 'parser', {'jsonBody': {'a': 1, 'b': 2}}, 'result', '''"a","b"\n1,2''', None),
    ('jscall', 'strictadder', {'a': 101, 'b': '2'},
        'result', None, 'Expected b to be of type "int", Got "str"'),
])
@pytest.mark.unit
def test__xf_jscall_remote_test(
    loaded_instance_manager,
    _type,
    _id,
    kwargs,
    result_key,
    result_value,
    error
):
    xf = loaded_instance_manager.get(_id, _type, TENANT)
    if not error:
        res = xf.test(json_body=kwargs)
        assert(res[result_key] == result_value)
    with pytest.raises(Exception) as aer:
        res = xf.test(json_body=kwargs)
        assert(aer == error)


@responses.activate
@pytest.mark.parametrize('_type,_id,kwargs,result_key,result_value,error', [
    ('restcall', 'simple', {
        'url': 'https://google.com', 'method': 'get'
    }, 'json', {'a': 1}, None),
    ('restcall', 'simple', {
        'url': 'http://localhost', 'method': 'get'
    }, 'json', {'a': 1}, 'DNS resolution failed for http://localhost'),
])
@pytest.mark.unit
def test__xf_rest_remote_test(
    loaded_instance_manager,
    _type,
    _id,
    kwargs,
    result_key,
    result_value,
    error
):
    url = kwargs.get('url')
    method_str = kwargs.get('method')
    method = responses.GET if method_str == 'get' else None
    body = json.dumps(result_value)
    responses.add(method, url, body=body, status=200)

    xf = loaded_instance_manager.get(_id, _type, TENANT)
    if not error:
        res = xf.test(json_body=kwargs)
        assert(res[result_key] == result_value)
    else:
        with pytest.raises(Exception) as aer:
            res = xf.test(json_body=kwargs)
            assert(aer == error)


@pytest.mark.unit
def test__pipelineset_simple():

    def _getter(*args, **kwargs):
        return transforms.JavascriptCall('_id', examples.XF_JS_ADDER, None)

    context = PipelineContext()
    context.register_result('source', {'one': 1})

    transition = {
        'input_map': {
            'a': '$.source.one',
            'b': '$.source.one'
        },
        'output_map': {'result': '$.result'}
    }
    stages = []
    for x in range(1, 10):
        name = f'stage{x}'
        stage = Stage(
            name, 'jscall', 'adder', Transition(**deepcopy(transition)), _getter)
        transition['input_map']['a'] = f'$.{name}.result'
        stages.append(stage)
    pipeline = PipelineSet('some-pipeline', 'sometenant', stages=stages)
    res = pipeline.run(context)
    assert(res.context.data['stage9'] == {'result': 10})


@pytest.mark.unit
def test__Pipeline_adder(loaded_instance_manager):
    p = artifacts.Pipeline(TENANT, examples.PIPELINE_SIMPLE, loaded_instance_manager)
    for x in range(5):
        result = p.test(**{
            'json_body': {'value': 100 + x}
        })
        assert(result.context.data['three']['result'] == 100 + x + 3)
    with pytest.raises(ConsumerHttpException):
        p.test(**{
            'json_body': {'value': 'a'}
        })

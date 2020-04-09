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

KAFKA_SUBSCRIPTION = {
    'id': 'sub-test',
    'name': 'Test Subscription',
    'topic_pattern': '*',
    'topic_options': {
        'masking_annotation': '@aether_masking',  # schema key for mask level of a field
        'masking_levels': ['public', 'private'],  # classifications
        'masking_emit_level': 'public',           # emit from this level ->
        'filter_required': False,                 # filter on a message value?
        'filter_field_path': 'operational_status',    # which field?
        'filter_pass_values': ['operational'],             # what are the passing values?
    }                                              # or hard-code like a/b/c
}

ZEEBE_INSTANCE = {}

ZEEBE_SUBSCRIPTION = {

}

PIPELINE = {
    'id': 'default',
    'name': 'something',
    'steps': [
    ]
}

BASE_TRANSFORMATION = {
    'id': 'test',
    'name': 'something'
}

BASE_TRANSITION = {
    'input_map': {'ref': '$.source.ref'},
    'output_map': {'ref': '$.ref'}
}

BASE_TRANSITION_PASS = dict(BASE_TRANSITION)
BASE_TRANSITION_PASS.update({
    'pass_condition': '$.ref.`match(200, null)`'
})

BASE_TRANSITION_FAIL = dict(BASE_TRANSITION)
BASE_TRANSITION_FAIL.update({
    'fail_condition': '$.ref.`notmatch(200, null)`'
})

XF_ZEEBE_SPAWN = {
    'id': 'echo',
    'name': 'echo',
    'workflow_name': 'flow',
    'spawn_mode': 'single',  # or multiple
    'iterable_source': '$.all_messages',
    # 'iterable_destination': 'message',
    # 'pass_condition': '$.source.status.`match(200, null)`',
    # 'input_map': {'ref': '$.source.ref'}
}

XF_ZEEBE_SPAWN_CONSTS = {
    'mode': 'multiple',
    'workflow': 'flow',
    'mapping': {},
    'message_iterator': '$.all_messages',
}

XF_JS_ADDER = {
    'id': 'test',
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
}

REST_TRANSFORMATION = {
    'id': 'echo',
    'name': 'echo',
}

ZEEBE_JOB = {
    'id': 'zeebe-default',
    'name': 'Default Stream Consumer Job',
    'zeebe_instance': 'default',
    'zeebe_subscription': 'default',
    'pipeline': 'default'
}

PIPELINE_SIMPLE = {
    'const': {
        'get_method': 'get',
        'entities_url': ''
    },
    'stages': []
}

ZEEBE_SINK = {}
KAFKA_SINK = {}


REST_STAGE = {
    'name': 'entities',
    'transform_type': 'restcall',
    'transform_id': None,
    'transition': {
        'input_map': {
            'method': '$.consts.get_method',
            'url': '$.consts.entities_url'
        },
        'output_map': {
            'status_code': '$.status_code',
            'messages': '$.json_body.results'
        }
    }
}

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
    'id': 'echo',
    'name': 'echo',
    'input_map': {'ref': '$.ref'},
    'output_map': {'ref': '$.ref'}
}

BASE_TRANSFORMATION_PASS = dict(BASE_TRANSFORMATION)
BASE_TRANSFORMATION_PASS.update({
    'pass_condition': '$.ref.`match(200, null)`'
})

BASE_TRANSFORMATION_FAIL = dict(BASE_TRANSFORMATION)
BASE_TRANSFORMATION_FAIL.update({
    'fail_condition': '$.ref.`notmatch(200, null)`'
})

XF_ZEEBE_SPAWN = {
    'id': 'echo',
    'name': 'echo',
    'workflow_name': 'flow',
    'spawn_mode': 'single',  # or multiple
    'iterable_source': '$.source.all_messages',
    'iterable_dest': 'message',
    'pass_condition': '$.source.status.`match(200, null)`',
    'input_map': {'ref': '$.source.ref'}
}

ZEEBE_JOB = {
    'id': 'zeebe-default',
    'name': 'Default Stream Consumer Job',
    'zeebe_instance': 'default',
    'zeebe_subscription': 'default',
    'pipeline': 'default'
}

ZEEBE_SINK = {}
KAFKA_SINK = {}

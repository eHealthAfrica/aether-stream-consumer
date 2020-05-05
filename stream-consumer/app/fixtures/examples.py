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

import os
from copy import deepcopy

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

ZEEBE_INSTANCE = {
    'id': 'default',
    'name': 'test_instance of ZB',
    'url': os.environ.get('ZEEBE_ADDRESS'),
    'client_id': os.environ.get('ZEEBE_CLIENT_ID'),
    'client_secret': os.environ.get('ZEEBE_CLIENT_SECRET'),
    'audience': os.environ.get('ZEEBE_AUDIENCE'),
    'token_url': os.environ.get('ZEEBE_AUTHORIZATION_SERVER_URL')
}

ZEEBE_SUBSCRIPTION = {

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

XF_ZEEBE_SPAWN_REQUIRED = {
    'id': 'default',
    'name': 'Needs other vars',
}

XF_ZEEBE_MESSAGE_REQUIRED = {
    'id': 'default',
    'name': 'Needs other vars',
}

XF_ZEEBE_COMPLETE_REQUIRED = {
    'id': 'default',
    'name': 'only needs transitions'
}

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
    'id': 'flow',
    'name': 'flow',
    'mode': 'multiple',
    'workflow': 'flow',
    'message_iterator': '$.all_messages',
}

XF_ZEEBE_SPAWN_REQUIRED = {
    'id': 'default',
    'name': 'Needs other vars',
}

XF_JS_ADDER = {
    'id': 'adder',
    'name': 'Laid Back JS Adder',
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

XF_JS_TYPED_ADDER = {
    'id': 'strictadder',
    'name': 'Adder with Type Checking',
    'entrypoint': 'f',
    'script': '''
        function adder(a, b) {
        return a + b;
    }
    function f(a, b) {
        return adder(a, b);
    }

    ''',
    'arguments': {'a': 'int', 'b': 'int'}
}

XF_JS_SIZER = {
    'id': 'sizer',
    'name': 'Sizes a JS object. Pretty useless.',
    'entrypoint': 'sizeOf',
    'script': '''

    function sizeOf( obj ) {

        var objectList = [];
        var stack = [ obj ];
        var bytes = 0;

        while ( stack.length ) {
            var value = stack.pop();

            if ( typeof value === 'boolean' ) {
                bytes += 4;
            }
            else if ( typeof value === 'string' ) {
                bytes += value.length * 2;
            }
            else if ( typeof value === 'number' ) {
                bytes += 8;
            }
            else if
            (
                typeof value === 'object'
                && objectList.indexOf( value ) === -1
            )
            {
                objectList.push( value );

                for( var i in value ) {
                    stack.push( value[ i ] );
                }
            }
        }
        return bytes;
    }
    ''',
    'arguments': ['obj']
}

XF_JS_ISODD = {
    'id': 'isodd',
    'name': 'Is it odd?',
    'entrypoint': 'f',
    'script': '''
    function f(value) {
        return (value % 2) != 0;
    }

    ''',
    'arguments': {'value': 'int'}
}

XF_JS_CSV_PARSER = {
    'id': 'parser',
    'name': 'CSV Parser',
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
}

REST_TRANSFORMATION = {
    'id': 'simple',
    'name': 'simple',
}

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

ZEEBE_JOB = {
    'id': 'zeebe-default',
    'name': 'Default Stream Consumer Job',
    'pipelines': ['default']
}


# uses Transforms Present in tests.loaded_instance_manager
PIPELINE_SIMPLE = {
    'id': 'add_something',
    'const': {
        'one': 1,
    },
    'stages': [
        {
            'name': 'one',
            'type': 'jscall',
            'id': 'strictadder',
            'transition': {
                'input_map': {
                    'a': '$.source.value',
                    'b': '$.const.one'
                },
                'output_map': {
                    'result': '$.result'
                }
            }
        },
        {
            'name': 'two',
            'type': 'jscall',
            'id': 'strictadder',
            'transition': {
                'input_map': {
                    'a': '$.one.result',
                    'b': '$.const.one'
                },
                'output_map': {
                    'result': '$.result'
                }
            }
        },
        {
            'name': 'three',
            'type': 'jscall',
            'id': 'strictadder',
            'transition': {
                'input_map': {
                    'a': '$.two.result',
                    'b': '$.const.one'
                },
                'output_map': {
                    'result': '$.result'
                }
            }
        }
    ]
}


PIPELINE_KAFKA = {
    'id': 'kafka',
    'name': 'something',
    'zeebe_instance': 'default',
    'kafka_subscription': deepcopy(KAFKA_SUBSCRIPTION),
    'const': {
        'process_id': 'sort-flow',
        'single': 'single',
        'message_listener': 'test_listener'
    },
    'stages': [
        {
            'name': 'one',
            'type': 'jscall',
            'id': 'sizer',
            'transition': {
                'input_map': {
                    'obj': '$.source.message'
                },
                'output_map': {
                    'result': '$.result'
                }
            }
        },
        {
            'name': 'two',
            'type': 'jscall',
            'id': 'isodd',
            'transition': {
                'input_map': {
                    'value': '$.one.result'
                },
                'output_map': {
                    'result': '$.result'
                }
            }
        },
        {
            'name': 'three',
            'type': 'zeebespawn',
            'id': 'default',
            'transition': {
                'input_map': {
                    'process_id': '$.const.process_id',
                    'mode': '$.const.single',
                    'isOdd': '$.two.result',
                    'message': '$.source.message'
                },
                'output_map': {
                    'isOdd': '$.isOdd',
                    'message': '$.message'
                }
            }
        },
        {
            'name': 'four',
            'type': 'zeebemessage',
            'id': 'default',
            'transition': {
                'input_map': {
                    'message_id': '$.source.message.id',
                    'listener_name': '$.const.message_listener',
                    'mode': '$.const.single',
                    'isOdd': '$.two.result'
                },
                'output_map': {
                    'isOdd': '$.isOdd'
                }
            }
        }
    ]
}

PIPELINE_ZEEBE = {
    'id': 'zeebe',
    'name': 'something',
    'zeebe_instance': 'default',
    'zeebe_subscription': 'odds-worker',
    'stages': [
        {
            'name': 'one',
            'type': 'zeebecomplete',
            'id': 'default',
            'transition': {
                'input_map': {
                    'message': '$.source.message'
                },
                'fail_condition': '$.source.isOdd'  # already a boolean
            }
        }
    ]
}

ZEEBE_SINK = {}
KAFKA_SINK = {}

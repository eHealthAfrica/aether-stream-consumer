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


# noqa: E501


# everything passes
PERMISSIVE = '''
{
    "$schema": "http://json-schema.org/draft-07/schema",
    "$id": "http://example.com/example.json",
    "type": "object",
    "title": "Permissive",
    "description": "Totally permissive, any object will pass."
}
'''

BASIC = '''
{
    "$schema": "http://json-schema.org/draft-07/schema",
    "$id": "http://example.com/example.json",
    "type": "object",
    "title": "Basic Requirements",
    "description": "The Minimum required for any Consumer Resource",
    "default": {},
    "additionalProperties": true,
    "required": [
        "id",
        "name"
    ],
    "properties": {
        "id": {
            "$id": "#/properties/id",
            "type": "string",
            "title": "ID",
            "description": "The ID used to reference the instance",
            "default": "",
            "examples": [
                "default"
            ]
        },
        "name": {
            "$id": "#/properties/name",
            "type": "string",
            "title": "Name",
            "description": "A description for the resource. Can be multiple works / include spaces",
            "default": "",
            "examples": [
                "Some Long Name"
            ]
        }
    }
}
'''

JS_CALL = '''
{
    "$schema": "http://json-schema.org/draft-07/schema",
    "$id": "http://example.com/example.json",
    "type": "object",
    "title": "Basic Requirements",
    "description": "The Minimum required for any Consumer Resource",
    "default": {},
    "additionalProperties": true,
    "required": [
        "id",
        "name",
        "arguments",
        "entrypoint"
    ],
    "properties": {
        "id": {
            "$id": "#/properties/id",
            "type": "string",
            "title": "ID",
            "description": "The ID used to reference the instance",
            "default": "",
            "examples": [
                "default"
            ]
        },
        "name": {
            "$id": "#/properties/name",
            "type": "string",
            "title": "Name",
            "description": "A description for the resource. Can be multiple works / include spaces",
            "default": "",
            "examples": [
                "Some Long Name"
            ]
        },
        "entrypoint": {
            "$id": "#/properties/entrypoint",
            "type": "string",
            "title": "The Entrypoint Schema",
            "description": "An explanation about the purpose of this instance.",
            "default": "",
            "examples": [
                "f"
            ]
        },
        "script": {
            "$id": "#/properties/script",
            "type": "string",
            "title": "The Script Schema",
            "description": "An explanation about the purpose of this instance.",
            "default": "",
            "examples": [
                ""
            ]
        },
        "arguments": {
                "oneOf": [
                    {"$ref": "#/definitions/argumentList"},
                    {"$ref": "#/definitions/argumentDict"}
                ]
            }
        },
    "definitions": {
        "argumentList": {
            "$id": "#/definitions/argumentList",
            "type": "array",
            "title": "The Arguments Schema",
            "description": "An explanation about the purpose of this instance.",
            "default": [],
            "examples": [
                [
                    "a",
                    "b"
                ]
            ],
            "additionalItems": true,
            "items": {
                "$id": "#/properties/arguments/items",
                "type": "string",
                "title": "The Items Schema",
                "description": "An explanation about the purpose of this instance.",
                "default": "",
                "examples": [
                    "a",
                    "b"
                ]
            }
        },
        "argumentDict": {
            "$id": "#/definitions/argumentDict",
            "type": "object",
            "title": "The Arguments Schema",
            "description": "An explanation about the purpose of this instance."
        }
    }
}
'''

KAFKA_MESSAGE = '''
{
    "$schema": "http://json-schema.org/draft-07/schema",
    "$id": "http://example.com/example.json",
    "type": "object",
    "title": "Basic Requirements",
    "description": "The Minimum required for any Consumer Resource",
    "default": {},
    "additionalProperties": true,
    "required": [
        "id",
        "name",
        "topic",
        "schema"
    ],
    "properties": {
        "id": {
            "$id": "#/properties/id",
            "type": "string",
            "title": "ID",
            "description": "The ID used to reference the instance",
            "examples": [
                "default"
            ]
        },
        "name": {
            "$id": "#/properties/name",
            "type": "string",
            "title": "Name",
            "description": "A description for the resource. Can be multiple works / include spaces",
            "examples": [
                "Some Long Name"
            ]
        },
        "topic": {
            "$id": "#/properties/topic",
            "type": "string",
            "title": "Write Topic",
            "description": "The topic name to be written to",
            "examples": [
                "my-topic"
            ]
        },
        "schema": {
            "$id": "#/properties/script",
            "type": "object",
            "title": "The Schema for the written object",
            "additionalProperties": true
        }
    }
}
'''

ZEEBE_INSTANCE = '''
{
    "$schema": "http://json-schema.org/draft-07/schema",
    "$id": "http://example.com/example.json",
    "type": "object",
    "title": "Zeebe Instance",
    "description": "Reference to a Zeebe Broker",
    "default": {},
    "additionalProperties": false,
    "required": [
        "id",
        "name"
    ],
    "properties": {
        "id": {
            "$id": "#/properties/id",
            "type": "string",
            "title": "ID",
            "description": "The ID used to reference the instance",
            "default": "",
            "examples": [
                "default"
            ]
        },
        "name": {
            "$id": "#/properties/name",
            "type": "string",
            "title": "Name",
            "description": "A description for the resource. Can be multiple works / include spaces",
            "default": "",
            "examples": [
                "Some Long Name"
            ]
        },
        "url": {
            "$id": "#/properties/url",
            "type": "string",
            "title": "Url",
            "description": "Broker URL",
            "default": "",
            "examples": [
                "zeebe-broker:26000"
            ]
        },
        "client_id": {
            "$id": "#/properties/client_id",
            "type": "string",
            "title": "Client ID",
            "description": "User for authentication",
            "default": "",
            "examples": [
                ""
            ]
        },
        "client_secret": {
            "$id": "#/properties/client_secret",
            "type": "string",
            "title": "Client Secret",
            "description": "Password for authentication",
            "default": "",
            "examples": [
                "password"
            ]
        },
        "audience": {
            "$id": "#/properties/audience",
            "type": "string",
            "title": "Audience",
            "description": "The auth audience, usually the same as the broker url",
            "default": "",
            "examples": [
                ""
            ]
        },
        "token_url": {
            "$id": "#/properties/token_url",
            "type": "string",
            "title": "Token URL",
            "description": "The url of the authentication server",
            "default": "",
            "examples": [
                ""
            ]
        }
    }
}
'''

JOB = '''
{
    "$schema": "http://json-schema.org/draft-07/schema",
    "$id": "http://example.com/example.json",
    "type": "object",
    "title": "Job",
    "description": "A Stream Consumer Job",
    "default": {},
    "additionalProperties": false,
    "required": [
        "id",
        "name",
        "pipelines"
    ],
    "properties": {
        "id": {
            "$id": "#/properties/id",
            "type": "string",
            "title": "ID",
            "description": "The ID used to reference the instance",
            "default": "",
            "examples": [
                "default"
            ]
        },
        "name": {
            "$id": "#/properties/name",
            "type": "string",
            "title": "Name",
            "description": "A description for the resource. Can be multiple works / include spaces",
            "default": "",
            "examples": [
                "Some Long Name"
            ]
        },
        "pipelines": {
            "$id": "#/properties/pipelines",
            "type": "array",
            "title": "The Pipelines Schema",
            "description": "An explanation about the purpose of this instance.",
            "default": [],
            "examples": [
                [
                    "rest_handler"
                ]
            ],
            "additionalItems": false,
            "items": {
                "$id": "#/properties/pipelines/items",
                "type": "string",
                "title": "PipelineID",
                "description": "ID of referenced Pipelines",
                "default": "",
                "examples": [
                    "default"
                ]
            }
        }
    }
}
'''

PIPELINE = '''
{
  "$schema": "http://json-schema.org/draft-07/schema",
  "$id": "http://example.com/example.json",
  "type": "object",
  "title": "The Root Schema",
  "description": "The root schema comprises the entire JSON document.",
  "default": {},
  "additionalProperties": false,
  "anyOf": [
    {
      "required": [
        "id",
        "zeebe_instance",
        "zeebe_subscription",
        "stages"
      ]
    },
    {
      "required": [
        "id",
        "kafka_subscription",
        "stages"
      ]
    }
  ],
  "definitions": {
    "error_handler": {
      "$id": "#definitions/error_handler",
      "type": "object",
      "title": "The Error Handler Schema",
      "required": [
        "error_topic"
      ],
      "additionalProperties": false,
      "properties": {
        "error_topic": {
          "$id": "#/properties/error_handler/properties/error_topic",
          "type": "string",
          "title": "ErrorEventTopic",
          "examples": [
            "The Topic to write error events"
          ],
          "pattern": "[a-z0-9.-]"
        },
        "log_errors": {
          "$id": "#/properties/error_handler/properties/log_errors",
          "type": "boolean",
          "title": "LogErrors",
          "default": true
        },
        "log_success": {
          "$id": "#/properties/error_handler/properties/log_success",
          "type": "boolean",
          "title": "LogSuccess",
          "default": false
        }
      }
    },
    "kafka_subscription": {
      "$id": "#definitions/kafka_subscription",
      "type": "object",
      "title": "The Root Schema",
      "required": [
        "topic_pattern"
      ],
      "properties": {
        "topic_pattern": {
          "$id": "#/properties/topic_pattern",
          "type": "string",
          "title": "The Topic_pattern Schema",
          "default": "",
          "examples": [
            "source topic for data i.e. gather*"
          ],
          "pattern": "^(.*)$"
        },
        "topic_options": {
          "$id": "#/properties/topic_options",
          "type": "object",
          "title": "The Topic_options Schema",
          "anyOf": [
            {
              "required": [
                "masking_annotation"
              ]
            },
            {
              "required": [
                "filter_required"
              ]
            }
          ],
          "dependencies": {
            "filter_required": [
              "filter_field_path",
              "filter_pass_values"
            ],
            "masking_annotation": [
              "masking_levels",
              "masking_emit_level"
            ]
          },
          "properties": {
            "masking_annotation": {
              "$id": "#/properties/topic_options/properties/masking_annotation",
              "type": "string",
              "title": "The Masking_annotation Schema",
              "default": "",
              "examples": [
                "@aether_masking"
              ],
              "pattern": "^(.*)$"
            },
            "masking_levels": {
              "$id": "#/properties/topic_options/properties/masking_levels",
              "type": "array",
              "title": "The Masking_levels Schema",
              "items": {
                "$id": "#/properties/topic_options/properties/masking_levels/items",
                "title": "The Items Schema",
                "examples": [
                  "private",
                  "public"
                ],
                "pattern": "^(.*)$"
              }
            },
            "masking_emit_level": {
              "$id": "#/properties/topic_options/properties/masking_emit_level",
              "type": "string",
              "title": "The Masking_emit_level Schema",
              "default": "",
              "examples": [
                "public"
              ],
              "pattern": "^(.*)$"
            },
            "filter_required": {
              "$id": "#/properties/topic_options/properties/filter_required",
              "type": "boolean",
              "title": "The Filter_required Schema",
              "default": false,
              "examples": [
                false
              ]
            },
            "filter_field_path": {
              "$id": "#/properties/topic_options/properties/filter_field_path",
              "type": "string",
              "title": "The Filter_field_path Schema",
              "default": "",
              "examples": [
                "some.json.path"
              ],
              "pattern": "^(.*)$"
            },
            "filter_pass_values": {
              "$id": "#/properties/topic_options/properties/filter_pass_values",
              "type": "array",
              "title": "The Filter_pass_values Schema",
              "items": {
                "$id": "#/properties/topic_options/properties/filter_pass_values/items",
                "title": "The Items Schema",
                "examples": [
                  false
                ]
              }
            }
          }
        }
      }
    },
    "stage": {
      "$id": "#/definitions/stage",
      "type": "object",
      "title": "The Stage Schema",
      "description": "An explanation about the purpose of this instance.",
      "default": {},
      "examples": [
        {
          "name": "one",
          "transition": {
            "fail_condition": "",
            "pass_condition": "",
            "output_map": {},
            "input_map": {}
          },
          "id": "default",
          "type": "restcall"
        }
      ],
      "additionalProperties": true,
      "required": [
        "name",
        "type",
        "id",
        "transition"
      ],
      "properties": {
        "name": {
          "$id": "#/properties/stage/properties/name",
          "type": "string",
          "title": "The Name Schema",
          "description": "An explanation about the purpose of this instance.",
          "default": "",
          "examples": [
            "one"
          ]
        },
        "type": {
          "$id": "#/properties/stage/properties/type",
          "type": "string",
          "title": "The Type Schema",
          "description": "An explanation about the purpose of this instance.",
          "default": "",
          "examples": [
            "restcall"
          ]
        },
        "id": {
          "$id": "#/properties/stage/properties/id",
          "type": "string",
          "title": "The Id Schema",
          "description": "An explanation about the purpose of this instance.",
          "default": "",
          "examples": [
            "default"
          ]
        },
        "transition": {
          "$id": "#/properties/stage/properties/transition",
          "type": "object",
          "title": "The Transition Schema",
          "description": "An explanation about the purpose of this instance.",
          "default": {},
          "examples": [
            {
              "pass_condition": "",
              "output_map": {},
              "input_map": {},
              "fail_condition": ""
            }
          ],
          "additionalProperties": false,
          "required": [],
          "properties": {
            "pass_condition": {
              "$id": "#/properties/stage/properties/transition/properties/pass_condition",
              "type": "string",
              "title": "The Pass_condition Schema",
              "description": "An explanation about the purpose of this instance.",
              "default": "",
              "examples": [
                ""
              ]
            },
            "fail_condition": {
              "$id": "#/properties/stage/properties/transition/properties/fail_condition",
              "type": "string",
              "title": "The Fail_condition Schema",
              "description": "An explanation about the purpose of this instance.",
              "default": "",
              "examples": [
                ""
              ]
            },
            "input_map": {
              "$id": "#/properties/stage/properties/transition/properties/input_map",
              "type": "object",
              "title": "The Input_map Schema",
              "description": "An explanation about the purpose of this instance.",
              "default": {},
              "examples": [
                {}
              ],
              "additionalProperties": true
            },
            "output_map": {
              "$id": "#/properties/stage/properties/transition/properties/output_map",
              "type": "object",
              "title": "The Output_map Schema",
              "description": "An explanation about the purpose of this instance.",
              "default": {},
              "examples": [
                {}
              ],
              "additionalProperties": true
            }
          }
        }
      }
    }},
  "properties": {
    "id": {
      "$id": "#/properties/id",
      "type": "string",
      "title": "The Id Schema",
      "description": "An explanation about the purpose of this instance.",
      "default": "",
      "examples": [
        "default"
      ]
    },
    "name": {
      "$id": "#/properties/name",
      "type": "string",
      "title": "The Name Schema",
      "description": "An explanation about the purpose of this instance.",
      "default": "",
      "examples": [
        "Some Name"
      ]
    },
    "zeebe_instance": {
      "$id": "#/properties/zeebe_instance",
      "type": "string",
      "title": "The Zeebe_instance Schema",
      "description": "An explanation about the purpose of this instance.",
      "default": "",
      "examples": [
        "default"
      ]
    },
    "zeebe_subscription": {
      "$id": "#/properties/zeebe_subscription",
      "type": "string",
      "title": "The Zeebe_subscription Schema",
      "description": "An explanation about the purpose of this instance.",
      "default": "",
      "examples": [
        "rest-worker"
      ]
    },
    "kafka_subscription": {
      "$ref": "#/definitions/kafka_subscription"
    },
    "error_handling": {
      "$ref": "#/definitions/error_handler"
    },
    "const": {
      "$id": "#/properties/const",
      "type": "object",
      "title": "The Const Schema",
      "description": "Constants made available to the pipeline at runtime"
    },
    "stages": {
      "$id": "#/properties/stages",
      "type": "array",
      "title": "The Stages Schema",
      "description": "An explanation about the purpose of this instance.",
      "default": [],
      "examples": [
        []
      ],
      "additionalItems": true,
      "items": {
        "$ref": "#/definitions/stage"
      }
    }
  }
}
'''

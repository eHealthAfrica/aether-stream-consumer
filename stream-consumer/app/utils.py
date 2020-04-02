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

from hashlib import md5
import json

# This is our general use hashing function
# Both for ensuring consistency in Kafka/FB
# and detecting config changes locally.


def hash(msg):
    sorted_msg = json.dumps(msg, sort_keys=True)
    encoded_msg = sorted_msg.encode('utf-8')
    hash = str(md5(encoded_msg).hexdigest())[:16]  # 64bit hash
    return hash

# These operations are for dealing with nested dictionaries
# Primarily for getting and setting config data

# _dict -> {"a":{"b":{"c":1}}} keys -> ["a","b"]
# = {"c":1}


def get_nested(_dict, keys):
    if len(keys) > 1:
        return get_nested(_dict[keys[0]], keys[1:])
    else:
        return _dict[keys[0]]

# _dict -> {"a":{"b":{"c":1}}} keys -> ["a","b"], value -> "new"
# =  {"a":{"b": "new"}}


def replace_nested(_dict, keys, value):
    if len(keys) > 1:
        _dict[keys[0]] = replace_nested(_dict[keys[0]], keys[1:], value)
    else:
        _dict[keys[0]] = value
    return _dict

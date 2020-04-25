#!/usr/bin/env python

# Copyright (C) 2020 by eHealth Africa : http://www.eHealthAfrica.org
#
# See the NOTICE file distributed with this work for additional information
# regarding copyright ownership.
#
# Licensed under the Apache License, Version 2.0 (the 'License');
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

import json

from zeebe_grpc import (
    gateway_pb2
)


class Event(object):
    def __init__(self, *args, **kwargs):
        pass


class TestEvent(Event, dict):
    # used for interactive testing
    def __init__(self, *args, **kwargs):
        # LOG.debug([args, kwargs])
        dict.__init__(self, *args, **kwargs)


class ZeebeJob(Event):
    def __init__(self, stub, job):
        self.key = job.key
        self.headers = json.loads(job.customHeaders)
        self.variables = json.loads(job.variables)
        self.stub = stub

    def complete(self, variables=None):
        self.stub.CompleteJob(
            gateway_pb2.CompleteJobRequest(
                jobKey=self.key,
                variables=json.dumps(variables) if variables else json.dumps({})))

    def fail(self, message=None):
        self.stub.FailJob(gateway_pb2.FailJobRequest(
            jobKey=self.key, errorMessage=message))

    def to_json(self):
        return {
            'key': self.key,
            'stub': 'NotSerializable',
            'variables': self.variables,
            'headers': self.headers
        }


class KafkaMessage(Event):
    def __init__(self, msg):
        self.key = msg.key
        self.topic = msg.topic
        self.value = msg.value
        self.schema = msg.schema

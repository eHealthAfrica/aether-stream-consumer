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

from dataclasses import dataclass
import json
import grpc
import requests
# import types
from zeebe_grpc import (
    gateway_pb2,
    gateway_pb2_grpc
)
# from aet.logger import get_logger
# LOG = get_logger('zeebe')


@dataclass
class ZeebeConfig:
    url: str
    client_id: str
    client_secret: str
    audience: str
    token_url: str


def get_credentials(config: ZeebeConfig):
    body = {
        'client_id': config.client_id,
        'client_secret': config.client_secret,
        'audience': config.audience
    }
    res = requests.post(config.token_url, json=body)
    res.raise_for_status()
    data = res.json()
    token = data['access_token']
    # default certificates
    ssl_creds = grpc.ssl_channel_credentials()
    call_creds = grpc.access_token_call_credentials(token)
    composite_credentials = grpc.composite_channel_credentials(ssl_creds, call_creds)
    return composite_credentials


def zboperation(fn):
    # wraps zeebe operations for ZeebeConnnections in a context manager
    # that handles auth / connection from the connection's ZeebeConfig
    def wrapper(*args, **kwargs):
        inst = args[0]
        try:
            try:
                with grpc.secure_channel(
                        *zb_connection_details(inst)) as channel:
                    kwargs['channel'] = channel
                    res = fn(*args, **kwargs)
                    # this is important for job_iterator to work
                    # without exiting the secure_channel context
                    yield from res
            except requests.exceptions.HTTPError as her:
                # we have to catch this and re-raise as otherwise
                # for some reason grpc._channel doesn't exist
                raise her
            except grpc._channel._InactiveRpcError:
                # expired token
                inst.credentials = None
                with grpc.secure_channel(
                        *zb_connection_details(inst)) as channel:
                    kwargs['channel'] = channel
                    res = fn(*args, **kwargs)
                    yield from res
        except requests.exceptions.HTTPError as her:
            raise her
    return wrapper


class ZeebeConnection(object):

    def __init__(self, config: ZeebeConfig):
        self.config = config
        self.credentials = None

    @zboperation
    def get_topology(self, channel=None):
        stub = gateway_pb2_grpc.GatewayStub(channel)
        topology = stub.Topology(gateway_pb2.TopologyRequest())
        return [topology]

    @zboperation
    def deploy_workflow(self, process_id, definition, channel=None):
        stub = gateway_pb2_grpc.GatewayStub(channel)
        workflow = gateway_pb2.WorkflowRequestObject(
            name=process_id,
            type=gateway_pb2.WorkflowRequestObject.BPMN,
            definition=definition
        )
        return [stub.DeployWorkflow(
            gateway_pb2.DeployWorkflowRequest(
                workflows=[workflow]
            )
        )]

    @zboperation
    def create_instance(self, process_id, variables=None, version=1, channel=None):
        stub = gateway_pb2_grpc.GatewayStub(channel)
        return [stub.CreateWorkflowInstance(
            gateway_pb2.CreateWorkflowInstanceRequest(
                bpmnProcessId=process_id,
                version=version,
                variables=json.dumps(variables) if variables else json.dumps({})
            )
        )]

    @zboperation
    def job_iterator(self, _type, worker_name, timeout=30, max=1, channel=None):
        stub = gateway_pb2_grpc.GatewayStub(channel)
        activate_jobs_response = stub.ActivateJobs(
            gateway_pb2.ActivateJobsRequest(
                type=_type,
                worker=worker_name,
                timeout=timeout,
                maxJobsToActivate=max
            )
        )
        for response in activate_jobs_response:
            for job in response.jobs:
                yield ZeebeJob(stub, job)


def zb_connection_details(inst: ZeebeConnection):
    if not inst.credentials:
        inst.credentials = get_credentials(inst.config)
    return [inst.config.url, inst.credentials]


class ZeebeJob(object):
    def __init__(self, stub, job):
        self.key = job.key
        self.variables = json.loads(job.variables)
        self.stub = stub

    def complete(self, variables=None):
        self.stub.CompleteJob(
            gateway_pb2.CompleteJobRequest(
                jobKey=self.key,
                variables=json.dumps(variables) if variables else json.dumps({})))

    def fail(self):
        self.stub.FailJob(gateway_pb2.FailJobRequest(jobKey=self.key))

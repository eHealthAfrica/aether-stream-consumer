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

from collections import OrderedDict
from dataclasses import dataclass
import json
import grpc
import pydoc
import quickjs
import requests
from requests.auth import HTTPBasicAuth
from typing import (Any, Callable, Dict, List, Tuple, Union, TYPE_CHECKING)  # noqa
from urllib.parse import urlparse
from zeebe_grpc import (
    gateway_pb2,
    gateway_pb2_grpc
)
import dns.resolver

from aet.jsonpath import CachedParser
from aet.resource import ResourceDefinition

# if TYPE_CHECKING:
#     from app.artifacts import Transformation
from aet.logger import get_logger
LOG = get_logger('zeebe')


class TransformationError(Exception):
    pass


def check_required(class_fields):
    def inner(f):
        def wrapper(*args, **kwargs):
            fields = [class_fields] if not isinstance(class_fields, list) else class_fields
            failed = []
            for field in fields:
                required = getattr(args[0], field)
                missing = [i for i in required if kwargs.get(i) is None]
                if missing:
                    failed.append('Expected required fields, missing {missing}')
            if len(failed) >= len(fields):
                raise RuntimeError(f'And '.join(failed))
            return f(*args, **kwargs)
        return wrapper
    return inner


@dataclass
class Transition:
    input_map: Dict
    output_map: Dict = None
    pass_condition: str = None
    fail_condition: str = None

    @staticmethod
    def handle_parser_results(matches):
        if matches:
            if len(matches) > 1:
                return [i.value for i in matches]
            else:
                return [i.value for i in matches][0]

    @staticmethod
    def apply_map(map: Dict, context: Dict) -> Dict:
        _mapped = {
            k: Transition.handle_parser_results(
                CachedParser.find(v, context)) for
            k, v in map.items()
        }
        # filter out nones so key presence doesn't cause overwrite on merge
        return {k: v for k, v in _mapped.items() if v is not None}

    @staticmethod
    def apply_merge_dicts(_map: Dict, a: Dict, b: dict):
        # source from A, then update with non None contents of B
        return {
            **Transition.apply_map(
                _map, a),
            **Transition.apply_map(
                _map, b)
        }

    def prepare_input(self, input_context: Dict, transformation: ResourceDefinition) -> Dict:
        return Transition.apply_merge_dicts(
            self.input_map,                      # source
            {'transformation': transformation},  # overrides
            input_context
        )

    def prepare_output(self, result: Dict, transformation: ResourceDefinition) -> Dict:
        return Transition.apply_merge_dicts(
            self.output_map,                     # source
            {'transformation': transformation},  # overrides
            result
        )

    def check_failure(self, output: Dict):
        path, result = self.get_evaluation_condition()
        if not path:
            return
        # raises Error on failure
        self.evaluate_condition(path, result, output)

    def evaluate_condition(self, path, expected, data):
        res = Transition.handle_parser_results(
            CachedParser.find(path, data))
        if res is expected:
            return
        raw_path = path.split('.`')[0]
        checksum = Transition.handle_parser_results(
            CachedParser.find(raw_path, data))
        raise ValueError(f'Expected {checksum} at path {raw_path} to evaluate '
                         f'to {expected} from expression {path}, got {res}')

    def get_evaluation_condition(self) -> Tuple[str, bool]:
        if self.pass_condition:
            return (self.pass_condition, True)
        elif self.fail_condition:
            return (self.fail_condition, False)
        # if no conditions, this stage always passes
        return (None, True)


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
            except (
                requests.exceptions.HTTPError,
                requests.exceptions.ConnectionError
            ) as her:
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


class Event(object):
    def __init__(self, *args, **kwargs):
        pass


class TestEvent(Event, dict):
    # used for interactive testing
    def __init__(self, *args, **kwargs):
        LOG.debug([args, kwargs])
        dict.__init__(self, *args, **kwargs)


class ZeebeJob(Event):
    def __init__(self, stub, job):
        self.key = job.key
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


# TODO implement for Kafka
class KafkaMessage(Event):
    pass


class RestHelper(object):

    resolver: dns.resolver.Resolver = None
    dns_cache = {}
    rest_calls = {  # Available calls mirrored in json schema
        'HEAD': requests.head,
        'GET': requests.get,
        'POST': requests.post,
        'PUT': requests.put,
        'DELETE': requests.delete,
        'OPTIONS': requests.options
    }

    required = [
        'method',
        'url'
    ]

    success_keys = [
        'encoding',
        'headers',
        'status_code',
        'text'
    ]

    failure_keys = [
        'encoding',
        'reason',
        'status_code'
    ]

    @classmethod
    def response_to_dict(cls, res):
        try:
            res.raise_for_status()
            data = {f: getattr(res, f) for f in cls.success_keys}
            try:
                data['json'] = res.json()
            except Exception:
                pass
            return data
        except requests.exceptions.HTTPError as her:
            return {f: getattr(her.response, f) for f in cls.failure_keys}

    @classmethod
    def request_type(cls, name: str):
        return cls.rest_calls.get(name)

    @classmethod
    def resolve(cls, url) -> bool:
        # using a specified DNS resolver to check hosts
        # keeps people from using this tool on the internal K8s network
        if not cls.resolver:
            cls.resolver = dns.resolver.Resolver()
            cls.resolver.nameservers = ['8.8.8.8', '8.8.4.4']
        url_obj = urlparse(url)
        host = url_obj.netloc
        if host in cls.dns_cache:
            return cls.dns_cache[host]
        try:
            cls.resolver.query(host)
            cls.dns_cache[host] = True
            return True
        except dns.resolver.NXDOMAIN:
            cls.dns_cache[host] = False
            return False
        except dns.resolver.NoAnswer:
            # probably malformed netloc, don't cache just in case.
            return False

    def __init__(self):
        pass

    @check_required('required')
    def request(
        self,
        method=None,
        url=None,
        headers=None,
        token=None,
        basic_auth=None,
        query_params=None,
        json_body=None,
        form_body=None,
        allow_redirects=False,
        **config
    ):
        # we can template the url with other config elements
        url = url.format(**config)
        if not self.resolve(url):
            raise RuntimeError(f'DNS resolution failed for {url}')
        fn = self.rest_calls[method.upper()]
        auth = HTTPBasicAuth(basic_auth['user'], basic_auth['password']) if basic_auth else None
        token = {'Authorization': f'access_token {token}'} if token else {}
        headers = headers or {}
        headers = {**token, **headers}  # merge in token if we have one
        request_kwargs = {
            'allow_redirects': allow_redirects,
            'auth': auth,
            'headers': headers,
            'params': query_params,
            'json': json_body,
            'data': form_body,
            'verify': False
        }
        res = fn(
            url,
            **request_kwargs
        )
        return self.response_to_dict(res)


class JSHelper(object):

    @staticmethod
    def get_file(url: str) -> str:
        res = requests.get(url)
        res.raise_for_status()
        return res.text

    def __init__(self, definition: ResourceDefinition):
        self._prepare_function(definition)
        self._prepare_arguments = self._make_argument_parser(definition.arguments)

    def _prepare_function(self, definition: ResourceDefinition):
        script = definition.script
        libs = definition.get('libraries', [])
        for lib_url in libs:
            _body = self.get_file(lib_url)
            script = f'''
                        {script}
                        {_body}
                        '''
        self._function = quickjs.Function(definition.entrypoint, script)

    def __type_checker(name, _type):
        if _type:
            _type = pydoc.locate(_type)

            def _fn(obj) -> bool:
                if not isinstance(obj, _type):
                    raise TypeError(f'Expected {name} to be of type {_type}, Got {type(_type)}')
                return True
            return _fn
        else:
            # no checking if _type is null
            def _fn(obj):
                return True
            return _fn

    def __make_type_checkers(self, args: Dict[str, str]) -> Dict[str, Callable]:
        return {name: self.__type_checker(_type) for name, _type in args.items()}

    def _make_argument_parser(self, args: Union[List[str], Dict[str, str]]):
        # TODO make type aware
        if isinstance(args, dict):
            type_checkers = self.__make_type_checkers(args)

            def _fn(input: Dict[str, Any]):
                return [input.get(i) for i in args if type_checkers[i](input.get(i))]
            return _fn
        elif isinstance(args, list):
            def _fn(input: Dict[str, Any]):
                return [input.get(i) for i in args]
            return _fn

    def calculate(self, input: Dict) -> Any:
        args = self._prepare_arguments(input)
        try:
            res = self._function(*args)
            return {'result': res}
        except Exception as err:
            raise TransformationError(err)


class PipelineContext(object):

    def __init__(
        self,
        event: Event = None,
        zeebe: ZeebeConnection = None,
        kafka=None  # Kafka instance (TODO add type)
    ):
        self.zeebe = zeebe
        self.kafka = kafka
        self.data: OrderedDict[str, Dict] = {}
        if isinstance(event, ZeebeJob):
            self.register_result('source', event.variables)
        elif isinstance(event, TestEvent):
            for k in event.keys():
                self.register_result(k, event.get(k))
        self.source_event = event

    def register_result(self, _id, result):
        self.data[_id] = result

    def last(self) -> Dict:
        return self.data.get(list(self.data.keys())[-1])

    def to_json(self):
        return json.dumps(self.data)


@dataclass
class Stage:
    name: str
    transform_type: str
    transform_id: str
    transition: Transition
    __transform_getter: Callable = None

    def run(self, context: PipelineContext):
        return self.__get_transformation().run(context, self.transition)

    def __get_transformation(self):  # -> Transformation:  # circular reference...
        # having a getter here helps make testing more easy to implement.
        return self.__transform_getter(self.transform_type, self.transform_id)


class PipelineSet(object):
    def __init__(
        self,
        definition: Dict = None,
        getter: Callable = None,
        stages: List[Stage] = None
    ):
        if stages:
            self.stages = stages
        else:
            if not all([definition, getter]):
                raise ValueError('PipelineSet requires definition and getter')
            self.stages = self._prepare_stages(definition, getter)

    def handle_event(event: Event):
        pass

    def _prepare_stages(self, definition, getter: Callable):
        return [
            Stage(
                st['name'],
                st['type'],
                st['id'],
                Transition(st['transition']),
                getter
            )
            for st in definition.stages
        ]

    def _execute_stage(
        self,
        stage: Stage,
        context: PipelineContext,
        raise_errors=True
    ):
        try:
            LOG.debug(f'{stage.name} Context : {json.dumps(context.data)}')
            result = stage.run(context)
            LOG.debug(f'{stage.name} Result : {json.dumps(result)}')
            context.register_result(stage.name, result)
        except TransformationError as ter:
            if raise_errors:
                raise(ter)
            else:
                context.register_result(stage.name, {'error': str(ter)})

    def run(self, context: PipelineContext, raise_errors=True):
        for stage in self.stages:
            self._execute_stage(stage, context, raise_errors)
        return context

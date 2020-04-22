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
from dataclasses import field as DataClassField
import enum
import json
import grpc
import pydoc
import quickjs
import requests
from requests.auth import HTTPBasicAuth
from typing import (  # noqa
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Tuple,
    Union
)
from urllib.parse import urlparse
from zeebe_grpc import (
    gateway_pb2,
    gateway_pb2_grpc
)
import dns.resolver

from aet.jsonpath import CachedParser
from aet.resource import ResourceDefinition
from aet.logger import get_logger
from aet.kafka import KafkaConsumer, FilterConfig, MaskConfig

from app.config import get_kafka_config

LOG = get_logger('hlpr')
KAFKA_CONFIG = get_kafka_config()


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
                    failed.append(f'Expected required fields, missing {missing}')
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
    client_id: str = None
    client_secret: str = None
    audience: str = None
    token_url: str = None
    is_secured: bool = DataClassField(init=False)

    def __post_init__(self):
        if not self.client_id:
            self.is_secured = False
        else:
            self.is_secured = True


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
                if inst.config.is_secured:
                    with grpc.secure_channel(
                            *zb_connection_details(inst)) as channel:
                        kwargs['channel'] = channel
                        res = fn(*args, **kwargs)
                        # this is important for job_iterator to work
                        # without exiting the secure_channel context
                        yield from res
                else:
                    with grpc.insecure_channel(inst.config.url) as channel:
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
                if inst.config.is_secured:
                    with grpc.secure_channel(
                            *zb_connection_details(inst)) as channel:
                        kwargs['channel'] = channel
                        res = fn(*args, **kwargs)
                        yield from res
                else:
                    with grpc.insecure_channel(inst.config.url) as channel:
                        kwargs['channel'] = channel
                        res = fn(*args, **kwargs)
                        # this is important for job_iterator to work
                        # without exiting the secure_channel context
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
    if not inst.credentials and inst.config.is_secured:
        inst.credentials = get_credentials(inst.config)
    return [inst.config.url, inst.credentials]


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
            'variables': self.variables
        }


# TODO implement for Kafka
class KafkaMessage(Event):
    def __init__(self, msg):
        self.key = msg.key
        self.topic = msg.topic
        self.value = msg.value
        self.schema = msg.schema


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
            data['headers'] = {k: v for k, v in data.get('headers', {}).items()}
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

    def __type_checker(self, name, _type):
        if _type:
            _type = pydoc.locate(_type)

            def _fn(obj) -> bool:
                if not isinstance(obj, _type):
                    raise TypeError(
                        f'Expected {name} to be of type "{_type.__name__}",'
                        f' Got "{type(obj).__name__}"')
                return True
            return _fn
        else:
            # no checking if _type is null
            def _fn(obj):
                return True
            return _fn

    def __make_type_checkers(self, args: Dict[str, str]) -> Dict[str, Callable]:
        return {name: self.__type_checker(name, _type) for name, _type in args.items()}

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


class PipelineConnection(enum.Enum):
    KAFKA = 1
    ZEEBE = 2


class PipelineContext(object):

    def __init__(
        self,
        event: Event = None,
        zeebe: ZeebeConnection = None,
        kafka_producer=None,  # Kafka instance (TODO add type)
        data: Dict = None  # other data to pass (consts, etc)
    ):
        self.zeebe = zeebe
        self.kafka = kafka_producer
        self.data: OrderedDict[str, Dict] = {}
        if isinstance(event, ZeebeJob):
            self.register_result('source', event.variables)
        elif isinstance(event, TestEvent):
            self.register_result('source', {
                k: event.get(k) for k in event.keys()
            })
        elif isinstance(event, KafkaMessage):
            self.register_result('source', {
                'message': event.value,
                'schema': event.schema,
                'key': event.key,
                'topic': event.topic
            })
        if data:
            for k in data.keys():
                self.register_result(k, data.get(k))
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
        try:
            return self.__get_transformation().run(context, self.transition)
        except AttributeError:
            raise TransformationError(
                f'Transformation type: "{self.transform_type}"'
                f' with id: "{self.transform_id}" not found.'
            )

    def __get_transformation(self) -> 'Transformation':  # noqa
        # having a getter here helps make testing more easy to implement.
        return self.__transform_getter(self.transform_id, self.transform_type)


class PipelinePubSub(object):
    def __init__(
        self,
        tenant: str,
        kafka_group=None,
        definition: Dict = None,
        zeebe: 'ZeebeInstance' = None  # noqa  type hint
    ):
        self.tenant = tenant
        self.kafka_group_id = kafka_group
        self.definition = definition
        self.kafka_consumer = None
        self.kafka_producer = None
        self.source_type = None
        self.zeebe: 'ZeebeInstance' = zeebe  # noqa
        self.zeebe_connection: ZeebeConnection = None

    def _make_context(self, evt: Event):
        data = {}
        if self.definition.get('const'):
            data = {'const': self.definition['const']}
        if not self.zeebe_connection:
            self.zeebe_connection = (None  # noqa
                if not self.zeebe \
                else self.zeebe.get_connection())
        return PipelineContext(
            evt,
            zeebe=self.zeebe_connection,
            kafka_producer=self.kafka_producer,
            data=data
        )

    def __message_getter(self):
        if not self.source_type:
            if 'kafka_subscription' in self.definition:
                self.source_type = PipelineConnection.KAFKA
                self.__source = self.__make_kafka_getter()

            elif 'zeebe_subscription' in self.definition:
                self.source_type = PipelineConnection.ZEEBE
                self.__source = self.__make_zeebe_getter()

        return self.__source

    def __make_kafka_getter(self):
        args = {k.lower(): v for k, v in KAFKA_CONFIG.copy().items()}
        args['group.id'] = self.kafka_group_id
        self.kafka_consumer = KafkaConsumer(**args)
        pattern = self.definition['kafka_subscription'].get('topic_pattern', '*')
        # only allow regex on the end of patterns
        if pattern.endswith('*'):
            topic = f'^{self.tenant}.{pattern}'
        else:
            topic = f'{self.tenant}.{pattern}'
        self.kafka_consumer.subscribe([topic], on_assign=self._on_kafka_assign)

        def _getter() -> Iterable[KafkaMessage]:
            messages = self.kafka_consumer.poll_and_deserialize(
                timeout=5,
                num_messages=1)
            for msg in messages:
                yield KafkaMessage(msg)
        return _getter

    def __make_zeebe_getter(self):
        workflow_id = self.definition.get('zeebe_subscription')
        if not self.zeebe_connection:
            self.zeebe_connection = (None  # noqa
                if not self.zeebe \
                else self.zeebe.get_connection())

        def _getter() -> Iterable[ZeebeJob]:
            jobs = self.zeebe_connection.job_iterator(workflow_id, self.kafka_group_id, max=50)
            c = 0
            for job in jobs:
                LOG.debug(f'got job: {json.dumps(job)}')
                c += 1
                yield job
            LOG.debug(f'No more jobs available on {workflow_id}, got {c}')
        return _getter

    def _get_events(self) -> Iterable[Event]:
        _source = self.__message_getter()
        yield from _source()

    def get(self) -> Iterable[PipelineContext]:
        evts: Iterable[Event] = self._get_events()
        for evt in evts:
            yield self._make_context(evt)

    def test(self, evt: Event) -> PipelineContext:
        return self._make_context(evt)

    # called when a subscription causes a new assignment to be given to the consumer
    def _on_kafka_assign(self, *args, **kwargs):
        assignment = args[1]
        topics = set([_part.topic for _part in assignment])
        for topic in list(topics):
            self._apply_consumer_filters(topic)

    def _apply_consumer_filters(self, topic):
        try:
            opts = self.definition['kafka_subscription']['topic_options']
            _flt = opts.get('filter_required', False)
            if _flt:
                _filter_options = {
                    'check_condition_path': opts.get('filter_field_path', ''),
                    'pass_conditions': opts.get('filter_pass_values', []),
                    'requires_approval': _flt
                }
                self.kafka_consumer.set_topic_filter_config(
                    topic,
                    FilterConfig(**_filter_options)
                )
            mask_annotation = opts.get('masking_annotation', None)
            if mask_annotation:
                _mask_options = {
                    'mask_query': mask_annotation,
                    'mask_levels': opts.get('masking_levels', []),
                    'emit_level': opts.get('masking_emit_level')
                }
                self.kafka_consumer.set_topic_mask_config(
                    topic,
                    MaskConfig(**_mask_options)
                )
        except AttributeError as aer:
            LOG.error(f'No topic options for {self._id}| {aer}')


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

    def _prepare_stages(self, definition, getter: Callable):
        return [
            Stage(
                st['name'],
                st['type'],
                st['id'],
                Transition(**st['transition']),
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
            # LOG.debug(f'{stage.name} Context : {json.dumps(context.data, indent=2)}')
            result = stage.run(context)
            # LOG.debug(f'{stage.name} Result : {json.dumps(result, indent=2)}')
            context.register_result(stage.name, result)
        except TransformationError as ter:
            if raise_errors:
                raise(ter)
            else:
                context.register_result(stage.name, {'error': str(ter)})

    def run(self, context: PipelineContext, raise_errors=True):
        for stage in self.stages:
            try:
                self._execute_stage(stage, context, raise_errors)
            except Exception as err:
                raise TransformationError(
                    f'On Stage "{stage.name}": {type(err).__name__}: {err}')
        return context

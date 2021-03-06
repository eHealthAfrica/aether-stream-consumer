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

import quickjs
import requests

from typing import (  # noqa
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Tuple,
    Union
)

from aet.resource import ResourceDefinition
from aet.logger import get_logger

from . import TransformationError, type_checker


LOG = get_logger('JS')


class JSHelper(object):

    @staticmethod
    def get_file(url: str) -> str:
        res = requests.get(url)
        res.raise_for_status()
        return res.text

    def __init__(self, definition: ResourceDefinition):
        self._function = None
        self.definition = definition
        try:
            self._setup()
        except Exception as err:
            LOG.critical(err)

    def _setup(self):
        self._prepare_function(self.definition)
        self._prepare_arguments = self._make_argument_parser(self.definition.arguments)

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

    def __make_type_checkers(self, args: Dict[str, str]) -> Dict[str, Callable]:
        return {name: type_checker(name, _type) for name, _type in args.items()}

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
        if not self._function:
            try:
                self._setup()
            except Exception as err:
                LOG.critical(err)
                raise TransformationError(f'could not setup jscall: {err}') from err
        args = self._prepare_arguments(input)
        try:
            res = self._function(*args)
            return {'result': res}
        except Exception as err:
            raise TransformationError(err)

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

from inspect import isclass
import pydoc


class TransformationError(Exception):
    pass


def type_checker(name, _type):
    _type = pydoc.locate(_type)
    if not isclass(_type):
        _type = None
    if _type:
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


def check_required(class_fields):
    def inner(f):
        def wrapper(*args, **kwargs):
            fields = [class_fields] if not isinstance(class_fields, list) else class_fields
            failed = []
            for field in fields:
                required = getattr(args[0], field)
                missing = []
                if isinstance(required, list):
                    missing = [i for i in required if kwargs.get(i) is None]
                elif isinstance(required, dict):
                    for name, expected_type in required.items():
                        value = kwargs.get(name)
                        if value is None:
                            missing.append(name)
                        else:
                            try:
                                type_checker(name, expected_type)(value)
                            except TypeError as ter:
                                failed.append(str(ter))
                if missing:
                    failed.append(f'Expected required fields, missing {missing}')

            if len(failed) >= len(fields):
                raise RuntimeError('And '.join(failed))
            return f(*args, **kwargs)
        return wrapper
    return inner

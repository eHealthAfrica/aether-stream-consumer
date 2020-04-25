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

import requests
from requests.auth import HTTPBasicAuth
from urllib.parse import urlparse

import dns.resolver

from . import check_required


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

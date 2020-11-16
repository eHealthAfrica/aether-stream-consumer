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

from io import BytesIO
import re
from typing import Callable, Dict, List, Union

from spavro import schema
from spavro.datafile import DataFileWriter
from spavro.io import (
    DatumWriter,
    validate as validate_schema
)

from aet.kafka_utils import create_topic, get_admin_client, get_broker_info

from app.config import get_kafka_admin_config


ADMIN_CONFIG = get_kafka_admin_config()
RE_VALID_KAFKA_TOPIC = re.compile(r'[a-z0-9.-]')


class TopicHelper(object):

    @staticmethod
    def parse(schema_definition) -> schema.Schema:
        return schema.parse(schema_definition)

    @staticmethod
    def valid_topic(name) -> bool:
        return RE_VALID_KAFKA_TOPIC.match(name) is not None and len(name) < 255

    def __init__(self, schema_definition, tenant, topic):
        self.schema = TopicHelper.parse(schema_definition)
        self.topic = f'{tenant}.{topic}'
        self.check_or_create_topic()

    def check_or_create_topic(self):
        kadmin = get_admin_client(ADMIN_CONFIG)
        info = get_broker_info(kadmin)
        if self.topic not in info.get('topics'):
            create_topic(kadmin, self.topic)

    def produce(self, doc: Union[Dict, List[Dict]], producer, callback: Callable = None):
        with BytesIO() as bytes_writer:
            writer = DataFileWriter(
                bytes_writer, DatumWriter(), schema, codec='deflate')
            if not isinstance(doc, list):
                doc = [doc]
            for row in doc:
                msg = row
                writer.append(msg)
            writer.flush()
            raw_bytes = bytes_writer.getvalue()

        producer.poll(0)
        producer.produce(
            self.topic,
            raw_bytes,
            callback=callback,
        )

    def validate(self, msg):
        return validate_schema(self.schema, msg)

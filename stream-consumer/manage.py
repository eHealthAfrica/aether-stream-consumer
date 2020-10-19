#!/usr/bin/env python

# Copyright (C) 2018 by eHealth Africa : http://www.eHealthAfrica.org
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

import signal
from time import sleep

from app.consumer import StreamConsumer
from app.config import consumer_config, kafka_config


from aet.logger import get_logger
LOG = get_logger('entry')


def wrapper(man):
    LOG.debug('setting signal handler')

    def fault(*args, **kwargs):
        man.dump_stack()
        man.stop()

    LOG.debug('signal handler ok')
    return fault


if __name__ == '__main__':
    try:
        manager = StreamConsumer(consumer_config, kafka_config)
        _fn = wrapper(manager)
        signal.signal(signal.SIGINT, _fn)
        LOG.debug('Started...')
        # while True:
        #     # LOG.debug(manager.dump_stack())
        #     LOG.debug(manager.healthcheck())
        #     sleep(1)
    except Exception as err:
        print('dead!')
        print(err)

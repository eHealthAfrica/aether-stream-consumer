from aet.consumer import BaseConsumer
from aet.logger import get_logger

from app import artifacts

LOG = get_logger('MAIN')


class StreamConsumer(BaseConsumer):

    def __init__(self, CON_CONF, KAFKA_CONF, redis_instance=None):
        self.job_class = artifacts.ZeebeJob
        super(StreamConsumer, self).__init__(
            CON_CONF,
            KAFKA_CONF,
            self.job_class,
            redis_instance=redis_instance
        )

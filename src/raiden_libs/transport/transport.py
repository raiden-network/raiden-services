import logging
from typing import List

import gevent
from eth_utils import is_address

log = logging.getLogger(__name__)


class Transport(gevent.Greenlet):
    """A generic transport class.

    Should be reimplemented to run registered callbacks whenever a message arrives.
    """
    def __init__(self):
        super().__init__()
        self.message_callbacks: List = list()

    def add_message_callback(self, callback):
        self.message_callbacks.append(callback)

    def _run(self):
        """Message receiving loop itself

        Implement this - a simple gevent Event sync will do"""
        raise NotImplementedError

    def transmit_data(self, data: str, target_node: str = None):
        """Send a single message over the transport """
        raise NotImplementedError

    def _validate_target(self, target: str = None):
        return is_address(target)

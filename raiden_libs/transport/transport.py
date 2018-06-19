import json
import logging
from typing import Union

import jsonschema
import gevent
from eth_utils import is_address

from raiden_libs.messages import Message
from raiden_libs.exceptions import MessageFormatError

log = logging.getLogger(__name__)


class Transport(gevent.Greenlet):
    """A generic transport class.

    Should be reimplemented to run registered callbacks whenever a message arrives.
    """
    def __init__(self):
        super().__init__()
        self.message_callbacks = list()

    def add_message_callback(self, callback):
        self.message_callbacks.append(callback)

    def run_message_callbacks(self, data):
        """Called whenever a message is received"""
        # ignore if message is not a JSON
        try:
            json_msg = json.loads(data)
        except json.decoder.JSONDecodeError as ex:
            log.error('Error when reading JSON: %s', str(ex))
            return

        # ignore message if JSON schema validation fails
        try:
            deserialized_msg = Message.deserialize(json_msg)
        except (
            jsonschema.exceptions.ValidationError,
            MessageFormatError,
        ) as ex:
            log.error('Error when deserializing message: %s', str(ex))
            return

        for callback in self.message_callbacks:
            callback(deserialized_msg)

    def _run(self):
        """Message receiving loop itself

        Implement this - a simple gevent Event sync will do"""
        raise NotImplementedError

    def send_message(self, message: Union[str, Message], target_node: str = None):
        """Wrapper that serializes Message type to a string, then sends it"""
        assert self._validate_target(target_node)
        assert isinstance(message, (str, Message))
        if isinstance(message, Message):
            message_str = message.serialize_full()
        else:
            message_str = message

        self.transmit_data(message_str, target_node)

    def transmit_data(self, data: str, target_node: str = None):
        """Send a single message over the transport """
        raise NotImplementedError

    def _validate_target(self, target: str = None):
        return is_address(target)

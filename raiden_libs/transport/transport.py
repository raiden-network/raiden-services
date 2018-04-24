import gevent
import json
import jsonschema
import logging
from raiden_libs.messages import Message
from raiden_libs.exceptions import MessageSignatureError, MessageFormatError

log = logging.getLogger(__name__)


class Transport(gevent.Greenlet):
    """A generic transport class.

    Should be reimplemented to run registered callbacks whenever a message arrives.
    """
    def __init__(self):
        super().__init__()
        self.message_callbacks = list()
        self._private_key = None

    @property
    def privkey(self):
        """Private key used to sign the messages"""
        if callable(self._private_key):
            return self._private_key()
        return self._private_key

    @privkey.setter
    def privkey(self, private_key):
        """Set key to sign messages sent over the transport"""
        assert isinstance(private_key, str) or callable(private_key)
        self._private_key = private_key

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
            MessageSignatureError,
            MessageFormatError
        ) as ex:
            log.error('Error when deserializing message: %s', str(ex))
            return

        for callback in self.message_callbacks:
            callback(deserialized_msg)

    def _run(self):
        """Message receiving loop itself

        Implement this - a simple gevent Event sync will do"""
        raise NotImplementedError

    def send_message(self, message):
        """Wrapper that serializes Message type to a string, then sends it"""
        assert isinstance(message, (str, Message))
        if isinstance(message, Message):
            message = message.serialize_full(self.privkey)
        self.transmit_data(message)

    def transmit_data(self, data):
        """Send a single message over the transport
        TODO: how to handle recipients?
        """
        raise NotImplementedError

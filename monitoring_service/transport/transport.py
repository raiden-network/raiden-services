import gevent
import json
from monitoring_service.messages import Message


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
        json_msg = json.loads(data)
        deserialized_msg = Message.deserialize(json_msg)
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
            data = message.serialize_full(self.privkey)
            data = json.dumps(data)
        self.transmit_data(data)

    def transmit_data(self, data):
        """Send a single message over the transport
        TODO: how to handle recipients?
        """
        raise NotImplementedError

from collections import defaultdict

import gevent

from raiden_libs.transport import Transport


class DummyTransport(Transport):
    """A simple dumb transport that implements required methods of Transport class."""
    def __init__(self):
        super().__init__()
        self.is_running = gevent.event.Event()
        self.received_messages = []
        self.sent_messages = defaultdict(list)

    def _run(self):
        self.is_running.wait()

    def receive_fake_data(self, data: str):
        """ Fakes that `data` was received and calls all callbacks. """
        self.received_messages.append(data)
        self.run_message_callbacks(data)

    def transmit_data(self, data: str, target_node: str = None):
        """Implements `transmit_data` method of the `Transport` class. """
        self.sent_messages[target_node].append(data)

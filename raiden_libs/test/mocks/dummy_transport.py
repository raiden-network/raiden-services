from raiden_libs.transport import Transport
import gevent


class DummyTransport(Transport):
    """A simple dumb transport that implements required methods of Transport class."""
    def __init__(self):
        super().__init__()
        self.is_running = gevent.event.Event()
        self.messages = []

    def _run(self):
        self.is_running.wait()

    def transmit_data(self, data: str):
        """Implements `transmit_data` method of the `Transport` class. Executes all registered
        callbacks using provided data."""
        self.messages.append(data)
        self.run_message_callbacks(data)

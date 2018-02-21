from monitoring_service.transport import Transport
import gevent


class DummyTransport(Transport):
    def __init__(self):
        super().__init__()
        self.is_running = gevent.event.Event()
        self.messages = []

    def _run(self):
        self.is_running.wait()

    def transmit_data(self, data: str):
        self.messages.append(data)
        self.run_message_callbacks(data)

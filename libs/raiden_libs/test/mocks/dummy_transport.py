from typing import List, Dict
from collections import defaultdict

import gevent

from raiden_libs.transport import Transport


class DummyNetwork:
    def __init__(self) -> None:
        self.nodes: Dict[str, Transport] = dict()

    def add_transport(self, address: str, transport: Transport):
        self.nodes[address] = transport

    def get_transport(self, address: str) -> Transport:
        return self.nodes[address]

    def dispatch_message(self, data: str, target: str):
        self.nodes[target].run_message_callbacks(data)
        self.nodes[target].received_messages.append(data)


class DummyTransport(Transport):
    """A simple dumb transport that implements required methods of Transport class."""
    def __init__(self, dummy_network: DummyNetwork = None) -> None:
        super().__init__()
        self.is_running = gevent.event.Event()
        self.received_messages: List[str] = []
        self.sent_messages: Dict[str, List[str]] = defaultdict(list)
        self.dummy_network = dummy_network

    def _run(self):
        self.is_running.wait()

    def receive_fake_data(self, data: str):
        """ Fakes that `data` was received and calls all callbacks. """
        self.received_messages.append(data)
        self.run_message_callbacks(data)

    def transmit_data(self, data: str, target_node: str = None):
        """Implements `transmit_data` method of the `Transport` class. """
        self.sent_messages[target_node].append(data)  # type: ignore

        if target_node and self.dummy_network:
            self.dummy_network.dispatch_message(data, target_node)

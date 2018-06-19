from typing import List

import pytest

from raiden_libs.test.mocks.client import MockRaidenNode
from raiden_libs.test.mocks.dummy_transport import DummyTransport, DummyNetwork


@pytest.fixture
def client_registry():
    """map: address => client"""
    return {}


@pytest.fixture
def generate_raiden_client(
        token_network,
        custom_token,
        get_random_privkey,
        client_registry,
        send_funds,
        ethereum_tester,
):
    """Factory function to create a new Raiden client. The client has some funds
    allocated by default and has no open channels."""
    def f():
        pk = get_random_privkey()
        ethereum_tester.add_account(pk)
        c = MockRaidenNode(pk, token_network, custom_token)
        c.client_registry = client_registry
        client_registry[c.address] = c
        send_funds(c.address)
        return c
    return f


@pytest.fixture
def generate_raiden_clients(web3, generate_raiden_client):
    """Factory function to generate a list of raiden clients."""
    def f(count=1):
        return [generate_raiden_client() for x in range(count)]
    return f


@pytest.fixture
def generate_dummy_network(generate_raiden_clients):
    """Factory function to generate a DummyNetwork full of Raiden clients with DummyTransports."""
    def f(count=2):
        clients: List[MockRaidenNode] = generate_raiden_clients(count)

        network = DummyNetwork()

        for client in clients:
            transport = DummyTransport(network)
            network.add_transport(client.address, transport)

            client.transport = transport

        return network, clients

    return f

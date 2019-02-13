import pytest

from raiden_libs.test.mocks.client import MockRaidenNode


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

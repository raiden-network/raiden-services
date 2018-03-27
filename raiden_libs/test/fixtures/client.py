import pytest
from eth_utils import denoms
from raiden_libs.test.mocks.client import MockRaidenNode


@pytest.fixture
def client_registry():
    """map: address => client"""
    return {}


@pytest.fixture
def generate_raiden_client(
        ethereum_tester,
        standard_token_network_contract,
        standard_token_contract,
        faucet_address,
        get_random_privkey,
        client_registry
):
    """Factory function to create a new Raiden client. The client has some funds
    allocated by default and has no open channels."""
    def f():
        pk = get_random_privkey()
        c = MockRaidenNode(pk, standard_token_network_contract)
        standard_token_contract.transact({'from': faucet_address}).transfer(
            c.address,
            10000
        )
        ethereum_tester.add_account(pk)
        c.token_contract = standard_token_contract
        c.client_registry = client_registry
        ethereum_tester.send_transaction({
            'from': faucet_address,
            'to': c.address,
            'gas': 21000,
            'value': 1 * denoms.ether
        })
        client_registry[c.address] = c
        return c
    return f


@pytest.fixture
def generate_raiden_clients(
        generate_raiden_client
):
    """Factory function to generate a list of raiden clients."""
    def f(count=1):
        return [generate_raiden_client() for x in range(count)]
    return f

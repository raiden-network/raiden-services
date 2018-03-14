import pytest
from eth_utils import denoms
from monitoring_service.test.mockups.client import MockRaidenNode


@pytest.fixture
def generate_raiden_client(
    ethereum_tester,
    channel_manager_contract,
    netting_channel_contract,
    standard_token_contract,
    faucet_address,
    get_random_privkey
):
    def f():
        pk = get_random_privkey()
        c = MockRaidenNode(pk, channel_manager_contract)
        c.netting_channel_abi = netting_channel_contract.abi
        standard_token_contract.transact({'from': faucet_address}).transfer(
            c.address,
            10000
        )
        ethereum_tester.add_account(pk)
        c.token_contract = standard_token_contract
        ethereum_tester.send_transaction({
            'from': faucet_address,
            'to': c.address,
            'gas': 21000,
            'value': 1 * denoms.ether
        })
        return c
    return f


@pytest.fixture
def generate_raiden_clients(
    generate_raiden_client
):
    def f(count=1):
        return [generate_raiden_client() for x in range(count)]
    return f

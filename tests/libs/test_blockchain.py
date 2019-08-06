import eth_tester
import pytest
from web3 import Web3

from raiden.utils.typing import Address, BlockNumber
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, EVENT_TOKEN_NETWORK_CREATED
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.blockchain import get_pessimistic_udc_balance, query_blockchain_events


def create_tnr_contract_events_query(
    web3: Web3, contract_manager: ContractManager, contract_address: Address
):
    def query_callback():
        return query_blockchain_events(
            web3=web3,
            contract_manager=contract_manager,
            contract_address=contract_address,
            contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
            topics=[],
            from_block=BlockNumber(0),
            to_block=web3.eth.blockNumber,
        )

    return query_callback


@pytest.mark.usefixtures("token_network")
def test_limit_inclusivity_in_query_blockchain_events(
    web3, wait_for_blocks, contracts_manager, token_network_registry_contract
):
    query = create_tnr_contract_events_query(
        web3, contracts_manager, token_network_registry_contract.address
    )

    # A new token network has been registered by the `token_network` fixture
    events = query()
    assert len(events) == 1
    event = events[0]
    assert event["event"] == EVENT_TOKEN_NETWORK_CREATED
    registry_event_block = BlockNumber(event["blockNumber"])

    # test to_block is inclusive
    events = query_blockchain_events(
        web3=web3,
        contract_manager=contracts_manager,
        contract_address=token_network_registry_contract.address,
        contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
        topics=[],
        from_block=BlockNumber(0),
        to_block=BlockNumber(registry_event_block - 1),
    )
    assert len(events) == 0

    events = query_blockchain_events(
        web3=web3,
        contract_manager=contracts_manager,
        contract_address=token_network_registry_contract.address,
        contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
        topics=[],
        from_block=BlockNumber(0),
        to_block=registry_event_block,
    )
    assert len(events) == 1

    # mine some more blocks
    wait_for_blocks(5)
    current_block_number = web3.eth.blockNumber
    assert current_block_number > registry_event_block

    # test to_block is inclusive
    events = query_blockchain_events(
        web3=web3,
        contract_manager=contracts_manager,
        contract_address=token_network_registry_contract.address,
        contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
        topics=[],
        from_block=BlockNumber(registry_event_block + 1),
        to_block=current_block_number,
    )
    assert len(events) == 0

    events = query_blockchain_events(
        web3=web3,
        contract_manager=contracts_manager,
        contract_address=token_network_registry_contract.address,
        contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
        topics=[],
        from_block=registry_event_block,
        to_block=current_block_number,
    )
    assert len(events) == 1

    # test that querying just one block works
    events = query_blockchain_events(
        web3=web3,
        contract_manager=contracts_manager,
        contract_address=token_network_registry_contract.address,
        contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
        topics=[],
        from_block=registry_event_block,
        to_block=registry_event_block,
    )
    assert len(events) == 1


def test_get_pessimistic_udc_balance(user_deposit_contract, web3, deposit_to_udc, get_accounts):
    address, = get_accounts(1)
    deposit_to_udc(address, 10)
    deposit_block = web3.eth.blockNumber
    web3.testing.mine(5)

    def deposit(from_offset, to_offset):
        return get_pessimistic_udc_balance(
            udc=user_deposit_contract,
            address=address,
            from_block=deposit_block + from_offset,
            to_block=deposit_block + to_offset,
        )

    assert deposit(0, 0) == 10
    assert deposit(0, 1) == 10
    assert deposit(0, 5) == 10
    assert deposit(-1, -1) == 0
    assert deposit(-1, 0) == 0
    assert deposit(-1, 1) == 0
    assert deposit(-5, 5) == 0

    # Hmm, I would expect this to fail, but maybe one block into the future is
    # allowed and will call into the block that is currently being created!?
    # with pytest.raises(eth_tester.exceptions.BlockNotFound):
    #     deposit(0, 6)

    # That's two blocks that do not exist, yet!
    with pytest.raises(eth_tester.exceptions.BlockNotFound):
        deposit(0, 7)

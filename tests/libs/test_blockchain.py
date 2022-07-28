from unittest.mock import patch

import eth_tester
import pytest
from eth_utils import to_canonical_address
from raiden_common.utils.typing import Address, BlockNumber, ChainID
from requests.exceptions import ReadTimeout
from web3 import Web3
from web3.contract import Contract

from monitoring_service.constants import DEFAULT_FILTER_INTERVAL
from raiden_contracts.constants import EVENT_TOKEN_NETWORK_CREATED
from raiden_libs.blockchain import (
    get_blockchain_events,
    get_blockchain_events_adaptive,
    get_pessimistic_udc_balance,
    query_blockchain_events,
)
from raiden_libs.states import BlockchainState


def create_tnr_contract_events_query(web3: Web3, contract_address: Address):
    def query_callback():
        return query_blockchain_events(
            web3=web3,
            contract_addresses=[contract_address],
            from_block=BlockNumber(0),
            to_block=web3.eth.block_number,
        )

    return query_callback


@pytest.mark.usefixtures("token_network")
def test_limit_inclusivity_in_query_blockchain_events(
    web3: Web3, wait_for_blocks, token_network_registry_contract
):
    query = create_tnr_contract_events_query(web3, token_network_registry_contract.address)

    # A new token network has been registered by the `token_network_registry_contract` fixture
    events = query()
    assert len(events) == 1
    event = events[0]
    assert event["event"] == EVENT_TOKEN_NETWORK_CREATED
    registry_event_block = BlockNumber(event["blockNumber"])

    # test to_block is inclusive
    events = query_blockchain_events(
        web3=web3,
        contract_addresses=[token_network_registry_contract.address],
        from_block=BlockNumber(0),
        to_block=BlockNumber(registry_event_block - 1),
    )
    assert len(events) == 0

    events = query_blockchain_events(
        web3=web3,
        contract_addresses=[token_network_registry_contract.address],
        from_block=BlockNumber(0),
        to_block=registry_event_block,
    )
    assert len(events) == 1

    # mine some more blocks
    wait_for_blocks(5)
    current_block_number = web3.eth.block_number
    assert current_block_number > registry_event_block

    # test to_block is inclusive
    events = query_blockchain_events(
        web3=web3,
        contract_addresses=[token_network_registry_contract.address],
        from_block=BlockNumber(registry_event_block + 1),
        to_block=current_block_number,
    )
    assert len(events) == 0

    events = query_blockchain_events(
        web3=web3,
        contract_addresses=[token_network_registry_contract.address],
        from_block=registry_event_block,
        to_block=current_block_number,
    )
    assert len(events) == 1

    # test that querying just one block works
    events = query_blockchain_events(
        web3=web3,
        contract_addresses=[token_network_registry_contract.address],
        from_block=registry_event_block,
        to_block=registry_event_block,
    )
    assert len(events) == 1


def test_get_pessimistic_udc_balance(user_deposit_contract, web3, deposit_to_udc, get_accounts):
    (address,) = get_accounts(1)
    deposit_to_udc(address, 10)
    deposit_block = web3.eth.block_number
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


def test_get_blockchain_events_returns_early_for_invalid_interval(
    web3: Web3, token_network_registry_contract: Contract
):
    events = get_blockchain_events(
        web3=web3,
        token_network_addresses=[],
        chain_state=BlockchainState(
            chain_id=ChainID(1),
            token_network_registry_address=to_canonical_address(
                token_network_registry_contract.address
            ),
            latest_committed_block=BlockNumber(4),
        ),
        from_block=BlockNumber(10),
        to_block=BlockNumber(5),
    )

    assert len(events) == 0


def test_get_blockchain_events_adaptive_reduces_block_interval_after_timeout(
    web3: Web3, token_network_registry_contract: Contract
):
    chain_state = BlockchainState(
        chain_id=ChainID(1),
        token_network_registry_address=to_canonical_address(
            token_network_registry_contract.address
        ),
        latest_committed_block=BlockNumber(4),
    )

    assert chain_state.current_event_filter_interval == DEFAULT_FILTER_INTERVAL

    with patch("raiden_libs.blockchain.get_blockchain_events", side_effect=ReadTimeout):
        _ = get_blockchain_events_adaptive(
            web3=web3,
            token_network_addresses=[],
            blockchain_state=chain_state,
            latest_confirmed_block=BlockNumber(1),
        )

        assert chain_state.current_event_filter_interval == DEFAULT_FILTER_INTERVAL // 5

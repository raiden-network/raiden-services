from web3 import Web3

from monitoring_service.blockchain import query_blockchain_events
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, EVENT_TOKEN_NETWORK_CREATED
from raiden_contracts.contract_manager import ContractManager


def create_tnr_contract_events_query(
    web3: Web3,
    contract_manager: ContractManager,
    contract_address: str,
):
    def f():
        return query_blockchain_events(
            web3=web3,
            contract_manager=contract_manager,
            contract_address=contract_address,
            contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
            topics=[],
            from_block=0,
            to_block=web3.eth.blockNumber,
        )
    return f


def test_limit_inclusivity_in_query_blockchain_events(
    web3,
    generate_raiden_clients,
    wait_for_blocks,
    contracts_manager,
    token_network_registry_contract,
):
    query = create_tnr_contract_events_query(
        web3,
        contracts_manager,
        token_network_registry_contract.address,
    )

    # this generates a new token network and registers it with the registry
    generate_raiden_clients(2)

    events = query()
    assert len(events) == 1
    event = events[0]
    assert event['event'] == EVENT_TOKEN_NETWORK_CREATED
    registry_event_block = event['blockNumber']

    # test to_block is inclusive
    events = query_blockchain_events(
        web3=web3,
        contract_manager=contracts_manager,
        contract_address=token_network_registry_contract.address,
        contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
        topics=[],
        from_block=0,
        to_block=registry_event_block - 1,
    )
    assert len(events) == 0

    events = query_blockchain_events(
        web3=web3,
        contract_manager=contracts_manager,
        contract_address=token_network_registry_contract.address,
        contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
        topics=[],
        from_block=0,
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
        from_block=registry_event_block + 1,
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

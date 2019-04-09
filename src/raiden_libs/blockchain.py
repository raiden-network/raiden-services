from copy import deepcopy
from typing import Dict, List, Tuple

import structlog
from eth_utils import decode_hex, encode_hex, to_checksum_address
from eth_utils.abi import event_abi_to_log_topic
from web3 import Web3
from web3.contract import get_event_data
from web3.utils.abi import filter_by_type

from raiden.utils.typing import ABI, BlockNumber
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    EVENT_TOKEN_NETWORK_CREATED,
    ChannelEvent,
    MonitoringServiceEvent,
)
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.events import (
    Event,
    ReceiveChannelClosedEvent,
    ReceiveChannelNewDepositEvent,
    ReceiveChannelOpenedEvent,
    ReceiveChannelSettledEvent,
    ReceiveMonitoringNewBalanceProofEvent,
    ReceiveMonitoringRewardClaimedEvent,
    ReceiveNonClosingBalanceProofUpdatedEvent,
    ReceiveTokenNetworkCreatedEvent,
    UpdatedHeadBlockEvent,
)
from raiden_libs.states import BlockchainState
from raiden_libs.types import Address

log = structlog.get_logger(__name__)


def create_registry_event_topics(contract_manager: ContractManager) -> List:
    new_network_abi = contract_manager.get_event_abi(
        CONTRACT_TOKEN_NETWORK_REGISTRY, EVENT_TOKEN_NETWORK_CREATED
    )
    return [encode_hex(event_abi_to_log_topic(new_network_abi))]


def decode_event(abi: ABI, log_: Dict) -> Dict:
    """ Helper function to unpack event data using a provided ABI

    Args:
        abi: The ABI of the contract, not the ABI of the event
        log_: The raw event data

    Returns:
        The decoded event
    """
    if isinstance(log_['topics'][0], str):
        log_['topics'][0] = decode_hex(log_['topics'][0])
    elif isinstance(log_['topics'][0], int):
        log_['topics'][0] = decode_hex(hex(log_['topics'][0]))
    event_id = log_['topics'][0]
    events = filter_by_type('event', abi)
    topic_to_event_abi = {event_abi_to_log_topic(event_abi): event_abi for event_abi in events}
    event_abi = topic_to_event_abi[event_id]
    return get_event_data(event_abi, log_)


def query_blockchain_events(
    web3: Web3,
    contract_manager: ContractManager,
    contract_address: Address,
    contract_name: str,
    topics: List,
    from_block: BlockNumber,
    to_block: BlockNumber,
) -> List[Dict]:
    """Returns events emmitted by a contract for a given event name, within a certain range.

    Args:
        web3: A Web3 instance
        contract_manager: A contract manager
        contract_address: The address of the contract to be filtered, can be `None`
        contract_name: The name of the contract
        topics: The topics to filter for
        from_block: The block to start search events
        to_block: The block to stop searching for events

    Returns:
        All matching events
    """
    filter_params = {
        'fromBlock': from_block,
        'toBlock': to_block,
        'address': to_checksum_address(contract_address),
        'topics': topics,
    }

    events = web3.eth.getLogs(filter_params)

    return [
        decode_event(ABI(contract_manager.get_contract_abi(contract_name)), raw_event)
        for raw_event in events
    ]


def get_blockchain_events(  # pylint: disable=too-many-branches
    web3: Web3,
    contract_manager: ContractManager,
    chain_state: BlockchainState,
    to_block: BlockNumber,
    query_ms: bool = True,
) -> Tuple[BlockchainState, List[Event]]:
    # increment by one, as latest_known_block has been queried last time already
    from_block = BlockNumber(chain_state.latest_known_block + 1)

    # Check if the current block was already processed
    if from_block > to_block:
        return chain_state, []

    new_chain_state = deepcopy(chain_state)
    log.info('Querying new block(s)', from_block=from_block, end_block=to_block)

    # first check for new token networks and add to state
    registry_events = query_blockchain_events(
        web3=web3,
        contract_manager=contract_manager,
        contract_address=new_chain_state.token_network_registry_address,
        contract_name=CONTRACT_TOKEN_NETWORK_REGISTRY,
        topics=create_registry_event_topics(contract_manager),
        from_block=from_block,
        to_block=to_block,
    )

    events: List[Event] = []
    for event in registry_events:
        token_network_address = event['args']['token_network_address']
        token_address = event['args']['token_address']
        block_number = event['blockNumber']

        events.append(
            ReceiveTokenNetworkCreatedEvent(
                token_address=token_address,
                token_network_address=token_network_address,
                block_number=block_number,
            )
        )
        new_chain_state.token_network_addresses.append(event['args']['token_network_address'])

    # then check all token networks
    for token_network_address in new_chain_state.token_network_addresses:
        network_events = query_blockchain_events(
            web3=web3,
            contract_manager=contract_manager,
            contract_address=Address(token_network_address),
            contract_name=CONTRACT_TOKEN_NETWORK,
            topics=[None],
            from_block=from_block,
            to_block=to_block,
        )

        for event in network_events:
            event_name = event['event']

            common_infos = dict(
                token_network_address=event['address'],
                channel_identifier=event['args']['channel_identifier'],
                block_number=event['blockNumber'],
            )

            if event_name == ChannelEvent.OPENED:
                events.append(
                    ReceiveChannelOpenedEvent(
                        participant1=event['args']['participant1'],
                        participant2=event['args']['participant2'],
                        settle_timeout=event['args']['settle_timeout'],
                        **common_infos,
                    )
                )
            elif event_name == ChannelEvent.DEPOSIT:
                events.append(
                    ReceiveChannelNewDepositEvent(
                        participant_address=event['args']['participant'],
                        total_deposit=event['args']['total_deposit'],
                        **common_infos,
                    )
                )
            elif event_name == ChannelEvent.CLOSED:
                events.append(
                    ReceiveChannelClosedEvent(
                        closing_participant=event['args']['closing_participant'], **common_infos
                    )
                )
            elif event_name == ChannelEvent.BALANCE_PROOF_UPDATED:
                events.append(
                    ReceiveNonClosingBalanceProofUpdatedEvent(
                        closing_participant=event['args']['closing_participant'],
                        nonce=event['args']['nonce'],
                        **common_infos,
                    )
                )
            elif event_name == ChannelEvent.SETTLED:
                events.append(ReceiveChannelSettledEvent(**common_infos))

    # get events from monitoring service contract
    if query_ms:
        monitoring_service_events = query_blockchain_events(
            web3=web3,
            contract_manager=contract_manager,
            contract_address=new_chain_state.monitor_contract_address,
            contract_name=CONTRACT_MONITORING_SERVICE,
            topics=[None],
            from_block=from_block,
            to_block=to_block,
        )
        for event in monitoring_service_events:
            event_name = event['event']
            block_number = event['blockNumber']

            if event_name == MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED:
                events.append(
                    ReceiveMonitoringNewBalanceProofEvent(
                        token_network_address=event['args']['token_network_address'],
                        channel_identifier=event['args']['channel_identifier'],
                        reward_amount=event['args']['reward_amount'],
                        nonce=event['args']['nonce'],
                        ms_address=event['args']['ms_address'],
                        raiden_node_address=event['args']['raiden_node_address'],
                        block_number=block_number,
                    )
                )
            elif event_name == MonitoringServiceEvent.REWARD_CLAIMED:
                events.append(
                    ReceiveMonitoringRewardClaimedEvent(
                        ms_address=event['args']['ms_address'],
                        amount=event['args']['amount'],
                        reward_identifier=encode_hex(event['args']['reward_identifier']),
                        block_number=block_number,
                    )
                )

    # commit new block number
    events.append(UpdatedHeadBlockEvent(head_block_number=to_block))

    return new_chain_state, events

from copy import deepcopy
from typing import Dict, List, Optional, Tuple

import structlog
from eth_abi.codec import ABICodec
from eth_utils import decode_hex, encode_hex, to_canonical_address, to_checksum_address
from eth_utils.abi import event_abi_to_log_topic
from web3 import HTTPProvider, Web3
from web3._utils.abi import filter_by_type
from web3.contract import Contract, get_event_data
from web3.types import ABIEvent, FilterParams, LogReceipt

from raiden.utils.typing import Address, BlockNumber, TokenAmount, TokenNetworkAddress
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
    ReceiveChannelOpenedEvent,
    ReceiveChannelSettledEvent,
    ReceiveMonitoringNewBalanceProofEvent,
    ReceiveMonitoringRewardClaimedEvent,
    ReceiveNonClosingBalanceProofUpdatedEvent,
    ReceiveTokenNetworkCreatedEvent,
    UpdatedHeadBlockEvent,
)
from raiden_libs.states import BlockchainState

log = structlog.get_logger(__name__)


def get_web3_provider_info(web3: Web3) -> str:
    """ Returns information about the provider

    Currently works only with `HTTPProvider`. Needs to be adapted when new procviders
    are added.
    """
    provider = web3.provider
    if isinstance(provider, HTTPProvider):
        endpoint = provider.endpoint_uri
        if endpoint is not None:
            return str(endpoint)

    raise RuntimeError(f"Unsupported web3 provider {provider!r}")


def create_registry_event_topics(contract_manager: ContractManager) -> List:
    new_network_abi = contract_manager.get_event_abi(
        CONTRACT_TOKEN_NETWORK_REGISTRY, EVENT_TOKEN_NETWORK_CREATED
    )
    # eth-utils doesn't have strict ABI types yet
    return [encode_hex(event_abi_to_log_topic(new_network_abi))]  # type: ignore


def decode_event(
    abi_codec: ABICodec, topic_to_event_abi: Dict[bytes, ABIEvent], log_entry: LogReceipt
) -> Dict:
    topic = log_entry["topics"][0]
    event_abi = topic_to_event_abi[topic]

    return get_event_data(abi_codec=abi_codec, event_abi=event_abi, log_entry=log_entry)


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
    events_abi = filter_by_type("event", contract_manager.get_contract_abi(contract_name))

    # eth-utils doesn't have strict ABI types yet
    topic_to_event_abi: Dict[bytes, ABIEvent] = {
        event_abi_to_log_topic(event_abi): event_abi for event_abi in events_abi  # type: ignore
    }

    filter_params = FilterParams(
        {
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": to_checksum_address(contract_address),
            "topics": topics,
        }
    )

    events = web3.eth.getLogs(filter_params)

    return [decode_event(web3.codec, topic_to_event_abi, log_entry) for log_entry in events]


def parse_token_network_event(event: dict) -> Optional[Event]:
    event_name = event["event"]

    common_infos = dict(
        token_network_address=decode_hex(event["address"]),
        channel_identifier=event["args"]["channel_identifier"],
        block_number=event["blockNumber"],
    )

    if event_name == ChannelEvent.OPENED:
        return ReceiveChannelOpenedEvent(
            participant1=to_canonical_address(event["args"]["participant1"]),
            participant2=to_canonical_address(event["args"]["participant2"]),
            settle_timeout=event["args"]["settle_timeout"],
            **common_infos,
        )
    if event_name == ChannelEvent.CLOSED:
        return ReceiveChannelClosedEvent(
            closing_participant=to_canonical_address(event["args"]["closing_participant"]),
            **common_infos,
        )
    if event_name == ChannelEvent.BALANCE_PROOF_UPDATED:
        return ReceiveNonClosingBalanceProofUpdatedEvent(
            closing_participant=to_canonical_address(event["args"]["closing_participant"]),
            nonce=event["args"]["nonce"],
            **common_infos,
        )
    if event_name == ChannelEvent.SETTLED:
        return ReceiveChannelSettledEvent(**common_infos)

    return None


def get_blockchain_events(
    web3: Web3,
    contract_manager: ContractManager,
    chain_state: BlockchainState,
    to_block: BlockNumber,
) -> Tuple[BlockchainState, List[Event]]:
    # increment by one, as `latest_committed_block` has been queried last time already
    from_block = BlockNumber(chain_state.latest_committed_block + 1)

    # Check if the current block was already processed
    if from_block > to_block:
        return chain_state, []

    new_chain_state = deepcopy(chain_state)
    log.info("Querying new block(s)", from_block=from_block, end_block=to_block)

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
    for event_dict in registry_events:
        token_network_address = TokenNetworkAddress(
            to_canonical_address(event_dict["args"]["token_network_address"])
        )
        events.append(
            ReceiveTokenNetworkCreatedEvent(
                token_network_address=token_network_address,
                token_address=to_canonical_address(event_dict["args"]["token_address"]),
                block_number=event_dict["blockNumber"],
            )
        )
        new_chain_state.token_network_addresses.append(token_network_address)

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

        for event_dict in network_events:
            event = parse_token_network_event(event_dict)
            if event:
                events.append(event)

    # get events from monitoring service contract, this only queries the chain
    # if the monitor contract address is set in chain_state
    monitoring_events = get_monitoring_blockchain_events(
        web3=web3,
        contract_manager=contract_manager,
        chain_state=new_chain_state,
        from_block=from_block,
        to_block=to_block,
    )
    events.extend(monitoring_events)

    # commit new block number
    events.append(UpdatedHeadBlockEvent(head_block_number=to_block))

    return new_chain_state, events


def get_monitoring_blockchain_events(
    web3: Web3,
    contract_manager: ContractManager,
    chain_state: BlockchainState,
    from_block: BlockNumber,
    to_block: BlockNumber,
) -> List[Event]:
    if chain_state.monitor_contract_address is None:
        return []

    monitoring_service_events = query_blockchain_events(
        web3=web3,
        contract_manager=contract_manager,
        contract_address=chain_state.monitor_contract_address,
        contract_name=CONTRACT_MONITORING_SERVICE,
        topics=[None],
        from_block=from_block,
        to_block=to_block,
    )

    events: List[Event] = []
    for event in monitoring_service_events:
        event_name = event["event"]
        block_number = event["blockNumber"]

        if event_name == MonitoringServiceEvent.NEW_BALANCE_PROOF_RECEIVED:
            events.append(
                ReceiveMonitoringNewBalanceProofEvent(
                    token_network_address=TokenNetworkAddress(
                        to_canonical_address(event["args"]["token_network_address"])
                    ),
                    channel_identifier=event["args"]["channel_identifier"],
                    reward_amount=event["args"]["reward_amount"],
                    nonce=event["args"]["nonce"],
                    ms_address=to_canonical_address(event["args"]["ms_address"]),
                    raiden_node_address=to_canonical_address(event["args"]["raiden_node_address"]),
                    block_number=block_number,
                )
            )
        elif event_name == MonitoringServiceEvent.REWARD_CLAIMED:
            events.append(
                ReceiveMonitoringRewardClaimedEvent(
                    ms_address=to_canonical_address(event["args"]["ms_address"]),
                    amount=event["args"]["amount"],
                    reward_identifier=encode_hex(event["args"]["reward_identifier"]),
                    block_number=block_number,
                )
            )

    return events


def get_pessimistic_udc_balance(
    udc: Contract, address: Address, from_block: BlockNumber, to_block: BlockNumber
) -> TokenAmount:
    """ Get the effective UDC balance using the block with the lowest result.

    Blocks between the latest confirmed block and the latest block are considered.
    """
    return min(
        udc.functions.effectiveBalance(address).call(block_identifier=BlockNumber(block))
        for block in range(from_block, to_block + 1)
    )

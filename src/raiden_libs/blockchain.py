import time
from typing import Dict, List, Optional

import structlog
from eth_abi.codec import ABICodec
from eth_utils import decode_hex, encode_hex, to_canonical_address
from eth_utils.abi import event_abi_to_log_topic
from requests.exceptions import ReadTimeout
from web3 import EthereumTesterProvider, HTTPProvider, Web3
from web3._utils.abi import filter_by_type
from web3.contract import Contract, get_event_data
from web3.types import ABIEvent, FilterParams, LogReceipt

from monitoring_service.constants import MAX_FILTER_INTERVAL, MIN_FILTER_INTERVAL
from raiden.constants import ETH_GET_LOGS_THRESHOLD_FAST, ETH_GET_LOGS_THRESHOLD_SLOW
from raiden.utils.typing import (
    Address,
    BlockNumber,
    BlockTimeout,
    TokenAddress,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    ChannelEvent,
    MonitoringServiceEvent,
)
from raiden_libs.contract_info import CONTRACT_MANAGER
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


def create_event_topic_to_abi_dict() -> Dict[bytes, ABIEvent]:
    contract_names = [
        CONTRACT_TOKEN_NETWORK_REGISTRY,
        CONTRACT_TOKEN_NETWORK,
        CONTRACT_MONITORING_SERVICE,
    ]

    event_abis = {}
    for contract_name in contract_names:
        events = filter_by_type("event", CONTRACT_MANAGER.get_contract_abi(contract_name))

        for event_abi in events:
            event_topic = event_abi_to_log_topic(event_abi)  # type: ignore
            event_abis[event_topic] = event_abi

    return event_abis  # type: ignore


EVENT_TOPIC_TO_ABI = create_event_topic_to_abi_dict()


def get_web3_provider_info(web3: Web3) -> str:
    """Returns information about the provider

    Currently works only with `HTTPProvider`. Needs to be adapted when new procviders
    are added.
    """
    provider = web3.provider
    if isinstance(provider, HTTPProvider):
        endpoint = provider.endpoint_uri
        if endpoint is not None:
            return str(endpoint)
    elif isinstance(provider, EthereumTesterProvider):
        return "EthereumTesterProvider"

    raise RuntimeError(f"Unsupported web3 provider {provider!r}")


def decode_event(abi_codec: ABICodec, log_entry: LogReceipt) -> Dict:
    topic = log_entry["topics"][0]
    event_abi = EVENT_TOPIC_TO_ABI[topic]

    return get_event_data(abi_codec=abi_codec, event_abi=event_abi, log_entry=log_entry)


def query_blockchain_events(
    web3: Web3, contract_addresses: List[Address], from_block: BlockNumber, to_block: BlockNumber
) -> List[Dict]:
    """Returns events emmitted by a contract for a given event name, within a certain range.

    Args:
        web3: A Web3 instance
        contract_addresses: The address(es) of the contract(s) to be filtered
        from_block: The block to start search events
        to_block: The block to stop searching for events

    Returns:
        All matching events
    """
    filter_params = FilterParams(
        {"fromBlock": from_block, "toBlock": to_block, "address": contract_addresses}
    )

    events = web3.eth.getLogs(filter_params)

    return [decode_event(web3.codec, log_entry) for log_entry in events]


def parse_token_network_event(event: dict) -> Optional[Event]:
    event_name = event["event"]

    # `DeprecationSwitch` isn't used currently, but needs to be checked so we can have
    # `channel_identifier` in `common_infos`
    # FIXME: use value from ChannelEvent as soon as PR is merged
    # https://github.com/raiden-network/raiden-contracts/pull/1389
    if event_name == "DeprecationSwitch":
        return None

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
    token_network_addresses: List[TokenNetworkAddress],
    chain_state: BlockchainState,
    from_block: BlockNumber,
    to_block: BlockNumber,
) -> List[Event]:
    # Check if the current block was already processed
    if from_block > to_block:
        return []

    log.info(
        "Querying new block(s)",
        from_block=from_block,
        to_block=to_block,
        # When `to_block` == `from_block` we query one block, so add one
        num_blocks=to_block - from_block + 1,
    )

    # first check for new token networks and add to state
    registry_events = query_blockchain_events(
        web3=web3,
        contract_addresses=[chain_state.token_network_registry_address],
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
                token_address=TokenAddress(
                    to_canonical_address(event_dict["args"]["token_address"])
                ),
                block_number=event_dict["blockNumber"],
            )
        )
        token_network_addresses.append(token_network_address)

    # then check all token networks
    network_events = query_blockchain_events(
        web3=web3,
        contract_addresses=token_network_addresses,  # type: ignore
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
        monitor_contract_address=chain_state.monitor_contract_address,
        from_block=from_block,
        to_block=to_block,
    )
    events.extend(monitoring_events)

    # commit new block number
    events.append(UpdatedHeadBlockEvent(head_block_number=to_block))

    return events


def get_monitoring_blockchain_events(
    web3: Web3,
    monitor_contract_address: Optional[Address],
    from_block: BlockNumber,
    to_block: BlockNumber,
) -> List[Event]:
    if monitor_contract_address is None:
        return []

    monitoring_service_events = query_blockchain_events(
        web3=web3,
        contract_addresses=[monitor_contract_address],
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
    """Get the effective UDC balance using the block with the lowest result.

    Blocks between the latest confirmed block and the latest block are considered.
    """
    return min(
        udc.functions.effectiveBalance(address).call(block_identifier=BlockNumber(block))
        for block in range(from_block, to_block + 1)
    )


def get_blockchain_events_adaptive(
    web3: Web3,
    blockchain_state: BlockchainState,
    token_network_addresses: List[TokenNetworkAddress],
    latest_confirmed_block: BlockNumber,
) -> Optional[List[Event]]:
    """
    Queries new events from the blockchain.

    Uses an adaptive interval, so that the ethereum nodes aren't overloaded.

    Args:
        web3: Web3 object
        blockchain_state: The blockchain state objected. This is mutated and should be reused.
        token_network_addresses: List of known token network addresses. This is mutated when a
            new token network is found. However, additionally a `ReceiveTokenNetworkCreatedEvent`
            is created as well and it is recommended to use that instead and to not reuse
            this list.
        latest_confirmed_block: The latest block to query to

    Returns:
        A list of events if successful, otherwise ``None``
    """
    # increment by one, as `latest_committed_block` has been queried last time already
    from_block = BlockNumber(blockchain_state.latest_committed_block + 1)
    to_block = min(
        latest_confirmed_block,
        # decrement by one, as both limits are inclusive
        BlockNumber(from_block + blockchain_state.current_event_filter_interval - 1),
    )

    try:
        before_query = time.monotonic()
        events = get_blockchain_events(
            web3=web3,
            token_network_addresses=token_network_addresses,
            chain_state=blockchain_state,
            from_block=from_block,
            to_block=to_block,
        )
        after_query = time.monotonic()

        filter_query_duration = after_query - before_query
        if filter_query_duration < ETH_GET_LOGS_THRESHOLD_FAST:
            blockchain_state.current_event_filter_interval = BlockTimeout(
                min(MAX_FILTER_INTERVAL, blockchain_state.current_event_filter_interval * 2)
            )
        elif filter_query_duration > ETH_GET_LOGS_THRESHOLD_SLOW:
            blockchain_state.current_event_filter_interval = BlockTimeout(
                max(MIN_FILTER_INTERVAL, blockchain_state.current_event_filter_interval // 2)
            )

        return events
    except ReadTimeout:
        old_interval = blockchain_state.current_event_filter_interval
        blockchain_state.current_event_filter_interval = BlockTimeout(
            max(MIN_FILTER_INTERVAL, old_interval // 5)
        )
        log.debug(
            "Failed to query events in time, reducing interval",
            old_interval=old_interval,
            new_interval=blockchain_state.current_event_filter_interval,
        )

    return None

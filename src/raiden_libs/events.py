from dataclasses import dataclass

from raiden_common.utils.typing import (
    Address,
    BlockNumber,
    Nonce,
    Timestamp,
    TokenAddress,
    TokenNetworkAddress,
)
from raiden_contracts.utils.type_aliases import ChannelID, TokenAmount


@dataclass(frozen=True)
class Event:  # pylint: disable=too-few-public-methods
    """Base class for events."""


@dataclass(frozen=True)
class ReceiveTokenNetworkCreatedEvent(Event):
    token_address: TokenAddress
    token_network_address: TokenNetworkAddress
    settle_timeout: Timestamp
    block_number: BlockNumber


@dataclass(frozen=True)
class ReceiveChannelOpenedEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    participant1: Address
    participant2: Address
    block_number: BlockNumber


@dataclass(frozen=True)
class ReceiveChannelClosedEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    closing_participant: Address
    block_number: BlockNumber


@dataclass(frozen=True)
class ReceiveNonClosingBalanceProofUpdatedEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    closing_participant: Address
    nonce: Nonce
    block_number: BlockNumber


@dataclass(frozen=True)
class ReceiveChannelSettledEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    block_number: BlockNumber


@dataclass(frozen=True)
class ReceiveMonitoringNewBalanceProofEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    reward_amount: TokenAmount
    nonce: Nonce
    ms_address: Address
    raiden_node_address: Address  # non_closing_participant
    block_number: BlockNumber


@dataclass(frozen=True)
class ReceiveMonitoringRewardClaimedEvent(Event):
    ms_address: Address
    amount: TokenAmount
    reward_identifier: str
    block_number: BlockNumber


@dataclass(frozen=True)
class UpdatedHeadBlockEvent(Event):
    """Event triggered after updating the head block and all events."""

    head_block_number: BlockNumber

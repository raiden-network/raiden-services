from dataclasses import dataclass

from raiden.utils.typing import Address, ChannelID, TokenNetworkAddress


class Event:
    """ Base class for events. """
    pass


@dataclass
class ReceiveChannelOpenedEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    participant1: Address
    participant2: Address
    settle_timeout: int
    block_number: int


@dataclass
class ReceiveChannelClosedEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    closing_participant: Address
    block_number: int


@dataclass
class ReceiveNonClosingBalanceProofUpdatedEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    closing_participant: Address
    nonce: int
    block_number: int


@dataclass
class ReceiveChannelSettledEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    block_number: int


@dataclass
class ReceiveMonitoringNewBalanceProofEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    reward_amount: int
    nonce: int
    ms_address: Address
    raiden_node_address: Address  # non_closing_participant
    block_number: int


@dataclass
class ReceiveMonitoringRewardClaimedEvent(Event):
    ms_address: Address
    amount: int
    reward_identifier: int
    block_number: int


@dataclass
class UpdatedHeadBlockEvent(Event):
    """ Event triggered after updating the head block and all events. """
    head_block_number: int


@dataclass
class ScheduledEvent(Event):
    """ An event to be triggered a t a certain block number. """
    trigger_block_number: int
    event: Event


@dataclass
class ActionMonitoringTriggeredEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    non_closing_participant: Address


@dataclass
class ActionClaimRewardTriggeredEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    non_closing_participant: Address

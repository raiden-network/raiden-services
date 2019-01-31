from dataclasses import dataclass


class Event:
    """ Base class for events. """
    pass


@dataclass
class ReceiveChannelOpenedEvent(Event):
    token_network_address: str
    channel_identifier: int
    participant1: str
    participant2: str
    settle_timeout: int
    block_number: int


@dataclass
class ReceiveChannelClosedEvent(Event):
    token_network_address: str
    channel_identifier: int
    closing_participant: str
    block_number: int


@dataclass
class ReceiveNonClosingBalanceProofUpdatedEvent(Event):
    token_network_address: str
    channel_identifier: int
    closing_participant: str
    nonce: int
    block_number: int


@dataclass
class ReceiveChannelSettledEvent(Event):
    token_network_address: str
    channel_identifier: int
    block_number: int


@dataclass
class ReceiveMonitoringNewBalanceProofEvent(Event):
    token_network_address: str
    channel_identifier: int
    reward_amount: int
    nonce: int
    ms_address: str
    raiden_node_address: str
    block_number: int


@dataclass
class ReceiveMonitoringRewardClaimedEvent(Event):
    ms_address: str
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
class ActionMonitoringTriggeredEvent:
    token_network_address: str
    channel_identifier: int


@dataclass
class ActionClaimRewardTriggeredEvent:
    token_network_address: str
    channel_identifier: int

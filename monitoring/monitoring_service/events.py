from dataclasses import dataclass


class Event:
    """ Base class for events. """
    pass


# Blockchain related events
# As in Raiden these are named ContractReceive*

@dataclass
class ContractReceiveTokenNetworkCreatedEvent(Event):
    token_network_address: str


@dataclass
class ContractReceiveChannelOpenedEvent(Event):
    token_network_address: str
    channel_identifier: int
    participant1: str
    participant2: str
    settle_timeout: int


@dataclass
class ContractReceiveChannelClosedEvent(Event):
    token_network_address: str
    channel_identifier: int
    closing_participant: str


@dataclass
class ContractReceiveNonClosingBalanceProofUpdatedEvent(Event):
    token_network_address: str
    channel_identifier: int
    closing_participant: str
    nonce: int


@dataclass
class ContractReceiveChannelSettledEvent(Event):
    token_network_address: str
    channel_identifier: int


@dataclass
class UpdatedHeadBlockEvent(Event):
    """ Event triggered after updating the head block and all events. """
    head_block_number: int

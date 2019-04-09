from dataclasses import dataclass

from raiden.utils.typing import BlockNumber, ChannelID
from raiden_libs.events import Event
from raiden_libs.types import Address, TokenNetworkAddress


@dataclass
class ScheduledEvent(Event):
    """ An event to be triggered a t a certain block number. """

    trigger_block_number: BlockNumber
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

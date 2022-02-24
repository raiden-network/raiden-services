from dataclasses import dataclass

from raiden.utils.typing import Address, ChannelID, Timestamp, TokenNetworkAddress
from raiden_libs.events import Event


@dataclass(frozen=True)
class ScheduledEvent(Event):
    """An event to be triggered a t a certain block number."""

    trigger_timestamp: Timestamp
    event: Event


@dataclass(frozen=True)
class ActionMonitoringTriggeredEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    non_closing_participant: Address


@dataclass(frozen=True)
class ActionClaimRewardTriggeredEvent(Event):
    token_network_address: TokenNetworkAddress
    channel_identifier: ChannelID
    non_closing_participant: Address

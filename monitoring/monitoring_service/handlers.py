from dataclasses import dataclass
from typing import List, cast

from web3 import Web3

from monitoring_service.database import Database
from monitoring_service.events import (
    ActionClaimRewardTriggeredEvent,
    ActionMonitoringTriggeredEvent,
    ContractReceiveChannelClosedEvent,
    ContractReceiveChannelOpenedEvent,
    ContractReceiveChannelSettledEvent,
    ContractReceiveNonClosingBalanceProofUpdatedEvent,
    ContractReceiveTokenNetworkCreatedEvent,
    Event,
    ScheduledEvent,
    UpdatedHeadBlockEvent,
)
from monitoring_service.states import Channel, MonitoringServiceState
from raiden_contracts.constants import ChannelState


@dataclass
class Context:
    ms_state: MonitoringServiceState
    db: Database
    scheduled_events: List[ScheduledEvent]
    w3: Web3


class EventHandler:
    """ Base class for event handlers.

    An event handler needs to be idempotent as events can be triggered
    multiple times.
    """
    def handle_event(self, event: Event):
        raise NotImplementedError


@dataclass
class TokenNetworkCreatedEventHandler(EventHandler):
    context: Context

    def handle_event(self, event: Event):
        if isinstance(event, ContractReceiveTokenNetworkCreatedEvent):
            print('Got new token network: ', event.token_network_address)
            self.context.ms_state.token_network_addresses.append(event.token_network_address)
            self.context.db.update_state(self.context.ms_state)


@dataclass
class ChannelOpenedEventHandler(EventHandler):
    context: Context

    def handle_event(self, event: Event):
        if isinstance(event, ContractReceiveChannelOpenedEvent):
            print('Adding channel to DB: ', event.channel_identifier)
            self.context.db.upsert_channel(
                Channel(
                    token_network_address=event.token_network_address,
                    identifier=event.channel_identifier,
                    participant1=event.participant1,
                    participant2=event.participant2,
                    settle_timeout=event.settle_timeout,
                ),
            )


@dataclass
class ChannelClosedEventHandler(EventHandler):
    context: Context
    # TODO: fixme
    wait_blocks: int = 100

    def handle_event(self, event: Event):
        if isinstance(event, ContractReceiveChannelClosedEvent):
            channel = self.context.db.get_channel(event.channel_identifier)

            if channel and channel.state == ChannelState.OPENED:
                print(
                    'Channel closed, triggering monitoring check',
                    channel.identifier,
                )

                # trigger the monitoring action by an event
                # TODO: check if we have a matching BP
                e = ActionMonitoringTriggeredEvent(
                    token_network_address=channel.token_network_address,
                    channel_identifier=channel.identifier,
                )
                trigger_block = event.block_number + self.wait_blocks
                self.context.scheduled_events.append(
                    ScheduledEvent(
                        trigger_block_number=trigger_block,
                        event=cast(Event, e),
                    ),
                )

                channel.state = ChannelState.CLOSED
                channel.closing_block = event.block_number
                self.context.db.upsert_channel(channel)
            else:
                print('Channel not in database')
                # FIXME: this is a bad error


@dataclass
class ChannelNonClosingBalanceProofUpdatedEventHandler(EventHandler):
    context: Context

    def handle_event(self, event: Event):
        if isinstance(event, ContractReceiveNonClosingBalanceProofUpdatedEvent):
            pass


@dataclass
class ChannelSettledEventHandler(EventHandler):
    context: Context

    # TODO: we might want to remove all related sstate here in the future
    #     for now we keep it to make debugging easier
    def handle_event(self, event: Event):
        if isinstance(event, ContractReceiveChannelSettledEvent):
            channel = self.context.db.get_channel(event.channel_identifier)

            if channel and channel.state == ChannelState.CLOSED:
                print('Received settle event for channel', event.channel_identifier)

                # trigger the claim reward action by an event
                # TODO: check if we did update the state
                e = ActionClaimRewardTriggeredEvent(
                    token_network_address=channel.token_network_address,
                    channel_identifier=channel.identifier,
                )
                trigger_block = event.block_number + channel.settle_timeout
                self.context.scheduled_events.append(
                    ScheduledEvent(
                        trigger_block_number=trigger_block,
                        event=cast(Event, e),
                    ),
                )

                channel.state = ChannelState.SETTLED
                self.context.db.upsert_channel(channel)
            else:
                print('Channel not in database')
                # FIXME: this is a bad error


@dataclass
class UpdatedHeadBlockEventHandler(EventHandler):
    """ Triggers commit of the new block number. """
    context: Context

    def handle_event(self, event: Event):
        if isinstance(event, UpdatedHeadBlockEvent):
            self.context.ms_state.latest_known_block = event.head_block_number
            self.context.db.update_state(self.context.ms_state)


@dataclass
class ActionMonitoringTriggeredEventHandler(EventHandler):
    context: Context

    def handle_event(self, event: Event):
        if isinstance(event, ActionMonitoringTriggeredEvent):
            print('Triggering channel monitoring')


@dataclass
class ActionClaimRewardTriggeredEventHandler(EventHandler):
    context: Context

    def handle_event(self, event: Event):
        if isinstance(event, ActionClaimRewardTriggeredEvent):
            print('Triggering reward claim')


HANDLERS = {
    ContractReceiveTokenNetworkCreatedEvent: TokenNetworkCreatedEventHandler,
    ContractReceiveChannelOpenedEvent: ChannelOpenedEventHandler,
    ContractReceiveChannelClosedEvent: ChannelClosedEventHandler,
    ContractReceiveNonClosingBalanceProofUpdatedEvent:
        ChannelNonClosingBalanceProofUpdatedEventHandler,
    ContractReceiveChannelSettledEvent: ChannelSettledEventHandler,
    UpdatedHeadBlockEvent: UpdatedHeadBlockEventHandler,
    ActionMonitoringTriggeredEvent: ActionMonitoringTriggeredEventHandler,
    ActionClaimRewardTriggeredEvent: ActionClaimRewardTriggeredEventHandler,
}

from dataclasses import dataclass

from monitoring_service.database import Database
from monitoring_service.events import (
    ContractReceiveChannelClosedEvent,
    ContractReceiveChannelOpenedEvent,
    ContractReceiveChannelSettledEvent,
    ContractReceiveNonClosingBalanceProofUpdatedEvent,
    ContractReceiveTokenNetworkCreatedEvent,
    Event,
    UpdatedHeadBlockEvent,
)
from monitoring_service.states import Channel, MonitoringServiceState
from raiden_contracts.constants import ChannelState


@dataclass
class Context:
    ms_state: MonitoringServiceState
    db: Database


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
                    identifier=event.channel_identifier,
                    participant1=event.participant1,
                    participant2=event.participant2,
                    settle_timeout=event.settle_timeout,
                ),
            )


@dataclass
class ChannelClosedEventHandler(EventHandler):
    context: Context

    def handle_event(self, event: Event):
        if isinstance(event, ContractReceiveChannelClosedEvent):
            channel = self.context.db.get_channel(event.channel_identifier)

            if channel and channel.state == ChannelState.OPENED:
                print(
                    'Channel closed, triggering monitoring check',
                    channel.identifier,
                )

                # trigger the monitoring action by an event
                # e = ActionMonitoringTriggeredEvent(channel.channel_identifier)
                # s.event_queue.append(e)

                channel.state = ChannelState.CLOSED
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

    def handle_event(self, event: Event):
        if isinstance(event, ContractReceiveChannelSettledEvent):
            channel = self.context.db.get_channel(event.channel_identifier)

            if channel:
                print('Received settle event for channel', event.channel_identifier)

                channel.state = ChannelState.SETTLED
                self.context.db.upsert_channel(channel)


@dataclass
class UpdatedHeadBlockEventHandler(EventHandler):
    """ Triggers commit of the new block number. """
    context: Context

    def handle_event(self, event: Event):
        if isinstance(event, UpdatedHeadBlockEvent):
            self.context.ms_state.latest_known_block = event.head_block_number
            self.context.db.update_state(self.context.ms_state)


HANDLERS = {
    ContractReceiveTokenNetworkCreatedEvent: TokenNetworkCreatedEventHandler,
    ContractReceiveChannelOpenedEvent: ChannelOpenedEventHandler,
    ContractReceiveChannelClosedEvent: ChannelClosedEventHandler,
    ContractReceiveNonClosingBalanceProofUpdatedEvent:
        ChannelNonClosingBalanceProofUpdatedEventHandler,
    ContractReceiveChannelSettledEvent: ChannelSettledEventHandler,
    UpdatedHeadBlockEvent: UpdatedHeadBlockEventHandler,
}

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
from raiden_contracts.constants import CONTRACT_MONITORING_SERVICE, ChannelState
from raiden_contracts.contract_manager import ContractManager


@dataclass
class Context:
    ms_state: MonitoringServiceState
    db: Database
    scheduled_events: List[ScheduledEvent]
    w3: Web3
    contract_manager: ContractManager


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
            channel = self.context.db.get_channel(
                event.token_network_address,
                event.channel_identifier,
            )

            if channel:
                print(
                    'Channel closed, triggering monitoring check',
                    channel.identifier,
                )

                # trigger the monitoring action by an event
                monitor_request = self.context.db.get_monitor_request(
                    token_network_address=channel.token_network_address,
                    channel_id=channel.identifier,
                )
                if monitor_request is not None:
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
                else:
                    print('No MR found for this channel, skipping')

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
            channel = self.context.db.get_channel(
                event.token_network_address,
                event.channel_identifier,
            )

            if channel:
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

            monitor_request = self.context.db.get_monitor_request(
                token_network_address=event.token_network_address,
                channel_id=event.channel_identifier,
            )

            if monitor_request is not None:
                # FIXME: don't monitor when closer is MR signer
                contract = self.context.w3.eth.contract(
                    abi=self.context.contract_manager.get_contract_abi(
                        CONTRACT_MONITORING_SERVICE,
                    ),
                    address=self.context.ms_state.monitor_contract_address,
                )
                tx_hash = contract.functions.monitor(
                    monitor_request.signer,
                    monitor_request.non_closing_signer,
                    monitor_request.balance_hash,
                    monitor_request.nonce,
                    monitor_request.additional_hash,
                    monitor_request.signature,
                    monitor_request.non_closing_signature,
                    monitor_request.reward_amount,
                    monitor_request.token_network_address,
                    monitor_request.reward_proof_signature,
                ).transact(
                    {'gas_limit': 350000},
                    private_key='',  # FIXME: use signing middleware
                )
                print(f'Submit MR to SC, got tx_hash {tx_hash}')
                assert tx_hash is not None
                # TODO: store tx hash in state
            else:
                print('Related MR not found, this is a bug')


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

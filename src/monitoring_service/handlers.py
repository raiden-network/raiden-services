from dataclasses import dataclass  # isort:skip noqa differences between local and travis
from typing import List, cast

import structlog
from eth_utils import encode_hex
from web3 import Web3

from monitoring_service.constants import WAIT_BLOCKS_BEFORE_MONITOR
from monitoring_service.database import Database
from monitoring_service.events import (
    ActionClaimRewardTriggeredEvent,
    ActionMonitoringTriggeredEvent,
    Event,
    ReceiveChannelClosedEvent,
    ReceiveChannelOpenedEvent,
    ReceiveChannelSettledEvent,
    ReceiveNonClosingBalanceProofUpdatedEvent,
    ScheduledEvent,
    UpdatedHeadBlockEvent,
    ReceiveMonitoringNewBalanceProofEvent,
    ReceiveMonitorinRewardClaimedEvent,
)
from monitoring_service.states import Channel, MonitoringServiceState
from raiden_contracts.constants import CONTRACT_MONITORING_SERVICE, ChannelState
from raiden_contracts.contract_manager import ContractManager

log = structlog.get_logger(__name__)


@dataclass
class Context:
    ms_state: MonitoringServiceState
    db: Database
    scheduled_events: List[ScheduledEvent]
    w3: Web3
    contract_manager: ContractManager
    last_known_block: int


def channel_opened_event_handler(event: Event, context: Context):
    assert isinstance(event, ReceiveChannelOpenedEvent)
    log.info(
        'Received new channel',
        token_network_address=event.token_network_address,
        identifier=event.channel_identifier,
    )
    context.db.upsert_channel(
        Channel(
            token_network_address=event.token_network_address,
            identifier=event.channel_identifier,
            participant1=event.participant1,
            participant2=event.participant2,
            settle_timeout=event.settle_timeout,
        ),
    )


def channel_closed_event_handler(event: Event, context: Context):
    assert isinstance(event, ReceiveChannelClosedEvent)
    channel = context.db.get_channel(
        event.token_network_address,
        event.channel_identifier,
    )

    if channel:
        log.info(
            'Channel closed, triggering monitoring check',
            token_network_address=event.token_network_address,
            identifier=channel.identifier,
        )

        # check if the settle timeout is already over
        # this is important when starting up the MS
        settle_period_end_block = event.block_number + channel.settle_timeout
        settle_period_over = (
            settle_period_end_block < context.last_known_block
        )
        # trigger the monitoring action by an event
        monitor_request = context.db.get_monitor_request(
            token_network_address=channel.token_network_address,
            channel_id=channel.identifier,
        )
        if monitor_request is not None and not settle_period_over:
            e = ActionMonitoringTriggeredEvent(
                token_network_address=channel.token_network_address,
                channel_identifier=channel.identifier,
            )
            trigger_block = event.block_number + WAIT_BLOCKS_BEFORE_MONITOR
            context.scheduled_events.append(
                ScheduledEvent(
                    trigger_block_number=trigger_block,
                    event=cast(Event, e),
                ),
            )
        else:
            if settle_period_over:
                log.info(
                    'Settle period timeout is in the past, skipping',
                    token_network_address=event.token_network_address,
                    identifier=channel.identifier,
                    settle_period_end_block=settle_period_end_block,
                    known_block=context.last_known_block,
                )
            else:
                log.info(
                    'No MR found for this channel, skipping',
                    token_network_address=event.token_network_address,
                    identifier=channel.identifier,
                )

        channel.state = ChannelState.CLOSED
        channel.closing_block = event.block_number
        context.db.upsert_channel(channel)
    else:
        log.warning('Channel not in database')
        # FIXME: this is a bad error


def channel_non_closing_balance_proof_updated_event_handler(event: Event, context: Context):
    assert isinstance(event, ReceiveNonClosingBalanceProofUpdatedEvent)


def channel_settled_event_handler(event: Event, context: Context):
    # TODO: we might want to remove all related state here in the future
    #     for now we keep it to make debugging easier
    assert isinstance(event, ReceiveChannelSettledEvent)
    channel = context.db.get_channel(
        event.token_network_address,
        event.channel_identifier,
    )

    if channel:
        log.info(
            'Received settle event for channel',
            token_network_address=event.token_network_address,
            identifier=event.channel_identifier,
        )

        # trigger the claim reward action by an event
        # TODO: check if we did update the state
        e = ActionClaimRewardTriggeredEvent(
            token_network_address=channel.token_network_address,
            channel_identifier=channel.identifier,
        )
        trigger_block = event.block_number + channel.settle_timeout
        context.scheduled_events.append(
            ScheduledEvent(
                trigger_block_number=trigger_block,
                event=cast(Event, e),
            ),
        )

        channel.state = ChannelState.SETTLED
        context.db.upsert_channel(channel)
    else:
        log.warning('Channel not in database')
        # FIXME: this is a bad error


def monitor_new_balance_proof_event_handler(event: Event, _context: Context):
    assert isinstance(event, ReceiveMonitoringNewBalanceProofEvent)
    log.info('Received MSC NewBalanceProof event', evt=event)


def monitor_reward_claim_event_handler(event: Event, _context: Context):
    assert isinstance(event, ReceiveMonitorinRewardClaimedEvent)
    log.info('Received MSC RewardClaimed event', evt=event)


def updated_head_block_event_handler(event: Event, context: Context):
    """ Triggers commit of the new block number. """
    assert isinstance(event, UpdatedHeadBlockEvent)
    context.ms_state.blockchain_state.latest_known_block = event.head_block_number
    context.db.update_state(context.ms_state)


def action_monitoring_triggered_event_handler(event: Event, context: Context):
    assert isinstance(event, ActionMonitoringTriggeredEvent)
    log.info('Triggering channel monitoring')

    monitor_request = context.db.get_monitor_request(
        token_network_address=event.token_network_address,
        channel_id=event.channel_identifier,
    )

    if monitor_request is not None:
        # FIXME: don't monitor when closer is MR signer
        contract = context.w3.eth.contract(
            abi=context.contract_manager.get_contract_abi(
                CONTRACT_MONITORING_SERVICE,
            ),
            address=context.ms_state.blockchain_state.monitor_contract_address,
        )
        try:
            tx_hash = contract.functions.monitor(
                monitor_request.signer,
                monitor_request.non_closing_signer,
                monitor_request.balance_hash,
                monitor_request.nonce,
                monitor_request.additional_hash,
                monitor_request.closing_signature,
                monitor_request.non_closing_signature,
                monitor_request.reward_amount,
                monitor_request.token_network_address,
                monitor_request.reward_proof_signature,
            ).transact({'gas': 100_000})  # TODO: estimate gas better here
            log.info(f'Submit MR to SC, got tx_hash {encode_hex(tx_hash)}')
            assert tx_hash is not None
            data = context.w3.eth.waitForTransactionReceipt(tx_hash)
            log.info('MINED', tx=data)
        except Exception as e:
            log.error('Sending tx failed', exc_info=True, err=e)
    else:
        log.warning('Related MR not found, this is a bug')


def action_claim_reward_triggered_event_handler(event: Event, context: Context):
    assert isinstance(event, ActionClaimRewardTriggeredEvent)
    log.info('Triggering reward claim')

    monitor_request = context.db.get_monitor_request(
        token_network_address=event.token_network_address,
        channel_id=event.channel_identifier,
    )

    if monitor_request is not None:
        contract = context.w3.eth.contract(
            abi=context.contract_manager.get_contract_abi(
                CONTRACT_MONITORING_SERVICE,
            ),
            address=context.ms_state.blockchain_state.monitor_contract_address,
        )

        try:
            tx_hash = contract.functions.claimReward(
                monitor_request.channel_identifier,
                monitor_request.token_network_address,
                monitor_request.signer,
                monitor_request.non_closing_signer,
            ).transact()
            receipt = context.w3.eth.getTransactionReceipt(tx_hash)
            log.info(receipt)
        except Exception as e:
            log.error('Sending tx failed', exc_info=True, err=e)
    else:
        log.warning('Related MR not found, this is a bug')

HANDLERS = {
    ReceiveChannelOpenedEvent: channel_opened_event_handler,
    ReceiveChannelClosedEvent: channel_closed_event_handler,
    ReceiveNonClosingBalanceProofUpdatedEvent:
        channel_non_closing_balance_proof_updated_event_handler,
    ReceiveChannelSettledEvent: channel_settled_event_handler,
    ReceiveMonitoringNewBalanceProofEvent: monitor_new_balance_proof_event_handler,
    ReceiveMonitorinRewardClaimedEvent: monitor_reward_claim_event_handler,
    UpdatedHeadBlockEvent: updated_head_block_event_handler,
    ActionMonitoringTriggeredEvent: action_monitoring_triggered_event_handler,
    ActionClaimRewardTriggeredEvent: action_claim_reward_triggered_event_handler,
}

from dataclasses import dataclass

import structlog
from eth_utils import encode_hex
from web3 import Web3
from web3.contract import Contract

from monitoring_service import metrics
from monitoring_service.database import Database
from monitoring_service.events import (
    ActionClaimRewardTriggeredEvent,
    ActionMonitoringTriggeredEvent,
    ScheduledEvent,
)
from monitoring_service.states import (
    Channel,
    MonitoringServiceState,
    MonitorRequest,
    OnChainUpdateStatus,
)
from raiden.utils.typing import BlockNumber, TokenNetworkAddress, TransactionHash
from raiden_contracts.constants import ChannelState
from raiden_libs.blockchain import get_pessimistic_udc_balance
from raiden_libs.constants import UDC_SECURITY_MARGIN_FACTOR_MS
from raiden_libs.events import (
    Event,
    ReceiveChannelClosedEvent,
    ReceiveChannelOpenedEvent,
    ReceiveChannelSettledEvent,
    ReceiveMonitoringNewBalanceProofEvent,
    ReceiveMonitoringRewardClaimedEvent,
    ReceiveNonClosingBalanceProofUpdatedEvent,
    ReceiveTokenNetworkCreatedEvent,
    UpdatedHeadBlockEvent,
)

log = structlog.get_logger(__name__)


@dataclass
class Context:
    ms_state: MonitoringServiceState
    database: Database
    web3: Web3
    monitoring_service_contract: Contract
    user_deposit_contract: Contract
    min_reward: int
    required_confirmations: int

    @property
    def latest_committed_block(self) -> BlockNumber:
        """The latest block for which all events have been processed and which
        has been written to the DB."""
        return self.ms_state.blockchain_state.latest_committed_block

    @property
    def latest_confirmed_block(self) -> BlockNumber:
        return BlockNumber(self.get_latest_unconfirmed_block() - self.required_confirmations)

    def get_latest_unconfirmed_block(self) -> BlockNumber:
        return self.web3.eth.block_number


def token_network_created_handler(event: Event, context: Context) -> None:
    assert isinstance(event, ReceiveTokenNetworkCreatedEvent)
    log.info(
        "Received new token network",
        token_network_address=event.token_network_address,
        token_address=event.token_address,
        token_network=event,
    )
    context.database.upsert_token_network(event.token_network_address)


def channel_opened_event_handler(event: Event, context: Context) -> None:
    assert isinstance(event, ReceiveChannelOpenedEvent)
    log.info(
        "Received new channel",
        token_network_address=event.token_network_address,
        identifier=event.channel_identifier,
        channel=event,
    )
    context.database.upsert_channel(
        Channel(
            token_network_address=event.token_network_address,
            identifier=event.channel_identifier,
            participant1=event.participant1,
            participant2=event.participant2,
            settle_timeout=event.settle_timeout,
        )
    )


def _first_allowed_block_to_monitor(
    token_network_address: TokenNetworkAddress, channel: Channel, context: Context
) -> BlockNumber:
    # Call smart contract to use its `firstBlockAllowedToMonitor` calculation
    return BlockNumber(
        context.monitoring_service_contract.functions.firstBlockAllowedToMonitorChannel(
            token_network=token_network_address,
            channel_identifier=channel.identifier,
            closing_participant=channel.participant1,
            non_closing_participant=channel.participant2,
            monitoring_service_address=context.ms_state.address,
        ).call()
    )


def channel_closed_event_handler(event: Event, context: Context) -> None:
    assert isinstance(event, ReceiveChannelClosedEvent)
    channel = context.database.get_channel(event.token_network_address, event.channel_identifier)

    if channel is None:
        log.error(
            "Channel not in database",
            token_network_address=event.token_network_address,
            identifier=event.channel_identifier,
        )
        metrics.get_metrics_for_label(metrics.ERRORS_LOGGED, metrics.ErrorCategory.STATE).inc()
        return

    # Check if the settle timeout is already over.
    # This is important when starting up the MS.
    settle_period_end_block = event.block_number + channel.settle_timeout
    settle_period_over = settle_period_end_block < context.latest_confirmed_block
    if not settle_period_over:
        # Trigger the monitoring action event handler, this will check if a
        # valid MR is available.
        # This enables the client to send a late MR
        # also see https://github.com/raiden-network/raiden-services/issues/29
        if channel.participant1 == event.closing_participant:
            non_closing_participant = channel.participant2
        else:
            non_closing_participant = channel.participant1

        # Transactions go into the next mined block, so we could trigger one block
        # before the `monitor` call is allowed to succeed to include it in the
        # first possible block.
        # Unfortunately, parity does the gas estimation on the current block
        # instead of the next one, so we have to wait for the first allowed
        # block to be finished to send the transaction successfully on parity.
        trigger_block = _first_allowed_block_to_monitor(
            event.token_network_address, channel, context
        )

        triggered_event = ActionMonitoringTriggeredEvent(
            token_network_address=channel.token_network_address,
            channel_identifier=channel.identifier,
            non_closing_participant=non_closing_participant,
        )

        log.info(
            "Channel closed, triggering monitoring check",
            token_network_address=event.token_network_address,
            identifier=channel.identifier,
            scheduled_event=triggered_event,
            trigger_block=trigger_block,
        )

        # Add scheduled event if it not exists yet. If the event is already
        # scheduled (e.g. after a restart) the DB takes care that it is only
        # stored once.
        context.database.upsert_scheduled_event(
            ScheduledEvent(trigger_block_number=trigger_block, event=triggered_event)
        )
    else:
        log.warning(
            "Settle period timeout is in the past, skipping",
            token_network_address=event.token_network_address,
            identifier=channel.identifier,
            settle_period_end_block=settle_period_end_block,
            latest_committed_block=context.latest_committed_block,
            latest_confirmed_block=context.latest_confirmed_block,
        )

    channel.state = ChannelState.CLOSED
    channel.closing_block = event.block_number
    channel.closing_participant = event.closing_participant
    context.database.upsert_channel(channel)


def non_closing_balance_proof_updated_event_handler(event: Event, context: Context) -> None:
    assert isinstance(event, ReceiveNonClosingBalanceProofUpdatedEvent)
    channel = context.database.get_channel(event.token_network_address, event.channel_identifier)

    if channel is None:
        log.error(
            "Channel not in database",
            token_network_address=event.token_network_address,
            identifier=event.channel_identifier,
        )
        metrics.get_metrics_for_label(metrics.ERRORS_LOGGED, metrics.ErrorCategory.STATE).inc()
        return

    log.info(
        "Received update event for channel",
        token_network_address=event.token_network_address,
        identifier=event.channel_identifier,
    )

    if event.closing_participant == channel.participant1:
        non_closing_participant = channel.participant2
    elif event.closing_participant == channel.participant2:
        non_closing_participant = channel.participant1
    else:
        log.error(
            "Update event contains invalid closing participant",
            participant1=channel.participant1,
            participant2=channel.participant2,
            closing_participant=event.closing_participant,
        )
        metrics.get_metrics_for_label(metrics.ERRORS_LOGGED, metrics.ErrorCategory.PROTOCOL).inc()
        return

    # check for known update calls and update accordingly
    if channel.update_status is None:
        log.info(
            "Creating channel update state",
            token_network_address=channel.token_network_address,
            channel_identifier=channel.identifier,
            new_nonce=event.nonce,
        )

        channel.update_status = OnChainUpdateStatus(
            update_sender_address=non_closing_participant, nonce=event.nonce
        )

        context.database.upsert_channel(channel)
    else:
        # nonce not bigger, should never happen as it is checked in the contract
        if event.nonce <= channel.update_status.nonce:
            log.error(
                "updateNonClosingBalanceProof nonce smaller than the known one, ignoring.",
                know_nonce=channel.update_status.nonce,
                received_nonce=event.nonce,
            )
            metrics.get_metrics_for_label(
                metrics.ERRORS_LOGGED, metrics.ErrorCategory.PROTOCOL
            ).inc()
            return

        log.info(
            "Updating channel update state",
            token_network_address=channel.token_network_address,
            channel_identifier=channel.identifier,
            new_nonce=event.nonce,
        )
        # update channel status
        channel.update_status.nonce = event.nonce
        channel.update_status.update_sender_address = non_closing_participant

        context.database.upsert_channel(channel)


def channel_settled_event_handler(event: Event, context: Context) -> None:
    # TODO: we might want to remove all related state here in the future
    #     for now we keep it to make debugging easier
    assert isinstance(event, ReceiveChannelSettledEvent)
    channel = context.database.get_channel(event.token_network_address, event.channel_identifier)

    if channel is None:
        log.error(
            "Channel not in database",
            token_network_address=event.token_network_address,
            identifier=event.channel_identifier,
        )
        metrics.get_metrics_for_label(metrics.ERRORS_LOGGED, metrics.ErrorCategory.STATE).inc()
        return

    log.info(
        "Received settle event for channel",
        token_network_address=event.token_network_address,
        identifier=event.channel_identifier,
    )

    channel.state = ChannelState.SETTLED
    context.database.upsert_channel(channel)


def monitor_new_balance_proof_event_handler(event: Event, context: Context) -> None:
    assert isinstance(event, ReceiveMonitoringNewBalanceProofEvent)
    channel = context.database.get_channel(event.token_network_address, event.channel_identifier)

    if channel is None:
        log.error(
            "Channel not in database",
            token_network_address=event.token_network_address,
            identifier=event.channel_identifier,
        )
        metrics.get_metrics_for_label(metrics.ERRORS_LOGGED, metrics.ErrorCategory.STATE).inc()
        return

    log.info(
        "Received MSC NewBalanceProof event",
        token_network_address=event.token_network_address,
        identifier=event.channel_identifier,
        evt=event,
    )

    # check for known monitor calls and update accordingly
    update_status = channel.update_status
    if update_status is None:
        log.info(
            "Creating channel update state",
            token_network_address=channel.token_network_address,
            channel_identifier=channel.identifier,
            new_nonce=event.nonce,
            new_sender=event.ms_address,
        )

        channel.update_status = OnChainUpdateStatus(
            update_sender_address=event.ms_address, nonce=event.nonce
        )

        context.database.upsert_channel(channel)
    else:
        # nonce not bigger, should never happen as it is checked in the contract
        if event.nonce < update_status.nonce:
            log.error(
                "MSC NewBalanceProof nonce smaller than the known one, ignoring.",
                know_nonce=update_status.nonce,
                received_nonce=event.nonce,
            )
            metrics.get_metrics_for_label(
                metrics.ERRORS_LOGGED, metrics.ErrorCategory.PROTOCOL
            ).inc()
            return

        log.info(
            "Updating channel update state",
            token_network_address=channel.token_network_address,
            channel_identifier=channel.identifier,
            new_nonce=event.nonce,
            new_sender=event.ms_address,
        )
        # update channel status
        update_status.nonce = event.nonce
        update_status.update_sender_address = event.ms_address

        context.database.upsert_channel(channel)

    # check if this was our update, if so schedule the call of
    # `claimReward` it will be checked there that our update was the latest one
    if event.ms_address == context.ms_state.address:
        assert channel.closing_block is not None, "closing_block not set"
        # Transactions go into the next mined block, so we could trigger one block
        # before the `claim` call is allowed to succeed to include it in the
        # first possible block.
        # Unfortunately, parity does the gas estimation on the current block
        # instead of the next one, so we have to wait for the first allowed
        # block to be finished to send the transaction successfully on parity.
        trigger_block = BlockNumber(channel.closing_block + channel.settle_timeout + 1)

        # trigger the claim reward action by an event
        triggered_event = ActionClaimRewardTriggeredEvent(
            token_network_address=channel.token_network_address,
            channel_identifier=channel.identifier,
            non_closing_participant=event.raiden_node_address,
        )

        log.info(
            "Received event for own update, triggering reward claim",
            token_network_address=event.token_network_address,
            identifier=channel.identifier,
            scheduled_event=triggered_event,
            trigger_block=trigger_block,
            closing_block=channel.closing_block,
            settle_timeout=channel.settle_timeout,
        )

        # Add scheduled event if it not exists yet
        # If the event is already scheduled (e.g. after a restart) the DB takes care that
        # it is only stored once
        context.database.upsert_scheduled_event(
            ScheduledEvent(trigger_block_number=trigger_block, event=triggered_event)
        )


def monitor_reward_claim_event_handler(event: Event, context: Context) -> None:
    assert isinstance(event, ReceiveMonitoringRewardClaimedEvent)

    if event.ms_address == context.ms_state.address:
        log.info(
            "Successfully claimed reward",
            amount=event.amount,
            reward_id=event.reward_identifier,
        )
        metrics.report_increased_reward_claims(event.amount, metrics.Who.US)
    else:
        log.debug(
            "Another MS claimed reward",
            amount=event.amount,
            reward_id=event.reward_identifier,
        )
        metrics.report_increased_reward_claims(event.amount, metrics.Who.THEY)


def updated_head_block_event_handler(event: Event, context: Context) -> None:
    """Triggers commit of the new block number."""
    assert isinstance(event, UpdatedHeadBlockEvent)
    context.ms_state.blockchain_state.latest_committed_block = event.head_block_number
    context.database.update_latest_committed_block(event.head_block_number)


def _is_mr_valid(monitor_request: MonitorRequest, channel: Channel) -> bool:
    if (
        monitor_request.signer not in channel.participants
        or monitor_request.non_closing_signer not in channel.participants
    ):
        log.info("MR signed by unknown party", channel=channel)
        return False

    if monitor_request.signer == monitor_request.non_closing_signer:
        log.info("MR signed by closing party", channel=channel)
        return False

    return True


def action_monitoring_triggered_event_handler(event: Event, context: Context) -> None:
    assert isinstance(event, ActionMonitoringTriggeredEvent)
    log.info("Triggering channel monitoring")

    monitor_request = context.database.get_monitor_request(
        token_network_address=event.token_network_address,
        channel_id=event.channel_identifier,
        non_closing_signer=event.non_closing_participant,
    )
    if monitor_request is None:
        log.error(
            "MonitorRequest cannot be found",
            token_network_address=event.token_network_address,
            channel_id=event.channel_identifier,
        )
        metrics.get_metrics_for_label(metrics.ERRORS_LOGGED, metrics.ErrorCategory.STATE).inc()
        return

    channel = context.database.get_channel(
        token_network_address=monitor_request.token_network_address,
        channel_id=monitor_request.channel_identifier,
    )
    if channel is None:
        log.error("Channel cannot be found", monitor_request=monitor_request)
        metrics.get_metrics_for_label(metrics.ERRORS_LOGGED, metrics.ErrorCategory.STATE).inc()
        return

    if not _is_mr_valid(monitor_request, channel):
        log.error(
            "MonitorRequest lost its validity",
            monitor_request=monitor_request,
            channel=channel,
        )
        metrics.get_metrics_for_label(metrics.ERRORS_LOGGED, metrics.ErrorCategory.PROTOCOL).inc()
        return

    last_onchain_nonce = 0
    if channel.update_status:
        last_onchain_nonce = channel.update_status.nonce

    if monitor_request.nonce <= last_onchain_nonce:
        log.info(
            "Another MS submitted the last known channel state",
            monitor_request=monitor_request,
        )
        return

    latest_block = context.web3.eth.block_number
    last_confirmed_block = context.latest_confirmed_block
    user_address = monitor_request.non_closing_signer
    user_deposit = get_pessimistic_udc_balance(
        udc=context.user_deposit_contract,
        address=user_address,
        from_block=last_confirmed_block,
        to_block=latest_block,
    )
    if monitor_request.reward_amount < context.min_reward:
        log.info(
            "Monitor request not executed due to insufficient reward amount",
            monitor_request=monitor_request,
            min_reward=context.min_reward,
        )
        return

    if user_deposit < monitor_request.reward_amount * UDC_SECURITY_MARGIN_FACTOR_MS:
        log.debug(
            "User deposit is insufficient -> try monitoring again later",
            monitor_request=monitor_request,
            min_reward=context.min_reward,
        )
        context.database.upsert_scheduled_event(
            ScheduledEvent(trigger_block_number=BlockNumber(last_confirmed_block + 1), event=event)
        )
        return

    assert (
        channel.monitor_tx_hash is None
    ), "This MS already monitored this channel. Should be impossible."

    try:
        # Attackers might be able to construct MRs that make this fail.
        # Since we execute a gas estimation before doing the `transact`,
        # the gas estimation will fail before any gas is used.
        # If we stop doing a gas estimation, a `call` has to be done before
        # the `transact` to prevent attackers from wasting the MS's gas.
        tx_hash = TransactionHash(
            bytes(
                context.monitoring_service_contract.functions.monitor(
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
                ).transact({"from": context.ms_state.address})
            )
        )
    except Exception as exc:  # pylint: disable=broad-except
        first_allowed = _first_allowed_block_to_monitor(
            event.token_network_address, channel, context
        )
        failed_at = context.web3.eth.block_number
        log.error(
            "Sending tx failed",
            exc_info=True,
            err=exc,
            first_allowed=first_allowed,
            failed_at=failed_at,
        )
        metrics.get_metrics_for_label(
            metrics.ERRORS_LOGGED, metrics.ErrorCategory.BLOCKCHAIN
        ).inc()
        return

    log.info(
        "Sent transaction calling `monitor` for channel",
        token_network_address=channel.token_network_address,
        channel_identifier=channel.identifier,
        transaction_hash=encode_hex(tx_hash),
    )
    assert tx_hash is not None

    with context.database.conn:
        # Add tx hash to list of waiting transactions
        context.database.add_waiting_transaction(tx_hash)

        channel.monitor_tx_hash = tx_hash
        context.database.upsert_channel(channel)


def action_claim_reward_triggered_event_handler(event: Event, context: Context) -> None:
    assert isinstance(event, ActionClaimRewardTriggeredEvent)
    log.info("Triggering reward claim")

    monitor_request = context.database.get_monitor_request(
        token_network_address=event.token_network_address,
        channel_id=event.channel_identifier,
        non_closing_signer=event.non_closing_participant,
    )
    if monitor_request is None:
        return

    channel = context.database.get_channel(
        token_network_address=monitor_request.token_network_address,
        channel_id=monitor_request.channel_identifier,
    )
    if channel is None:
        return

    # check that the latest update was ours and that we didn't send a transaction yet
    can_claim = (
        channel.claim_tx_hash is None
        and channel.update_status is not None
        and channel.update_status.update_sender_address == context.ms_state.address
    )
    log.info("Checking if eligible for reward", reward_available=can_claim)

    # check if claiming will produce a reward
    has_reward = monitor_request.reward_amount > 0
    if not has_reward:
        log.warning(
            "MonitorRequest has no reward. Skipping reward claim.",
            reward_amount=monitor_request.reward_amount,
            monitor_request=monitor_request,
        )

    if can_claim and has_reward:
        try:
            # The gas estimation will prevent us from wasting gas on failing
            # transactions. Attackers shouldn't be able to exploit this
            # transaction to waste gas anyway unless there is a bug in the smart
            # contract. It should not be possible to bring the contract into a
            # state where MS has a reward, the contract says it is time to
            # claim it, but the claim will fail.
            tx_hash = TransactionHash(
                bytes(
                    context.monitoring_service_contract.functions.claimReward(
                        monitor_request.channel_identifier,
                        monitor_request.token_network_address,
                        monitor_request.signer,
                        monitor_request.non_closing_signer,
                    ).transact({"from": context.ms_state.address})
                )
            )

            log.info(
                "Sent transaction calling `claimReward` for channel",
                token_network_address=channel.token_network_address,
                channel_identifier=channel.identifier,
                transaction_hash=encode_hex(tx_hash),
            )
            assert tx_hash is not None

            with context.database.conn:
                # Add tx hash to list of waiting transactions
                context.database.add_waiting_transaction(tx_hash)

                channel.claim_tx_hash = tx_hash
                context.database.upsert_channel(channel)
        except Exception as exc:  # pylint: disable=broad-except
            log.error("Sending tx failed", exc_info=True, err=exc)

            metrics.get_metrics_for_label(
                metrics.ERRORS_LOGGED, metrics.ErrorCategory.PROTOCOL
            ).inc()
            # manually increase exception counter here because
            # exception is not visible from outside
            metrics.EVENTS_EXCEPTIONS_RAISED.labels(event_type=event.__class__.__name__).inc()


HANDLERS = {
    ReceiveTokenNetworkCreatedEvent: token_network_created_handler,
    ReceiveChannelOpenedEvent: channel_opened_event_handler,
    ReceiveChannelClosedEvent: channel_closed_event_handler,
    ReceiveNonClosingBalanceProofUpdatedEvent: non_closing_balance_proof_updated_event_handler,
    ReceiveChannelSettledEvent: channel_settled_event_handler,
    ReceiveMonitoringNewBalanceProofEvent: monitor_new_balance_proof_event_handler,
    ReceiveMonitoringRewardClaimedEvent: monitor_reward_claim_event_handler,
    UpdatedHeadBlockEvent: updated_head_block_event_handler,
    ActionMonitoringTriggeredEvent: action_monitoring_triggered_event_handler,
    ActionClaimRewardTriggeredEvent: action_claim_reward_triggered_event_handler,
}

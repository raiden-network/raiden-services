# pylint: disable=redefined-outer-name
from typing import Optional
from unittest.mock import Mock, patch

import pytest
from eth_utils import to_checksum_address
from tests.libs.mocks.web3 import Web3Mock
from tests.monitoring.monitoring_service.factories import (
    DEFAULT_CHANNEL_IDENTIFIER,
    DEFAULT_PARTICIPANT1,
    DEFAULT_PARTICIPANT2,
    DEFAULT_SETTLE_TIMEOUT,
    DEFAULT_TOKEN_NETWORK_ADDRESS,
    create_signed_monitor_request,
)

from monitoring_service.database import Database
from monitoring_service.events import (
    ActionClaimRewardTriggeredEvent,
    ActionMonitoringTriggeredEvent,
    ScheduledEvent,
)
from monitoring_service.handlers import (
    Context,
    action_claim_reward_triggered_event_handler,
    action_monitoring_triggered_event_handler,
    channel_closed_event_handler,
    channel_opened_event_handler,
    channel_settled_event_handler,
    monitor_new_balance_proof_event_handler,
    monitor_reward_claim_event_handler,
    non_closing_balance_proof_updated_event_handler,
    updated_head_block_event_handler,
)
from monitoring_service.states import OnChainUpdateStatus
from raiden.utils.typing import Address, BlockNumber, BlockTimeout, ChannelID, Nonce, TokenAmount
from raiden_contracts.constants import ChannelState
from raiden_contracts.tests.utils import get_random_privkey
from raiden_libs.constants import UDC_SECURITY_MARGIN_FACTOR_MS
from raiden_libs.events import (
    Event,
    ReceiveChannelClosedEvent,
    ReceiveChannelOpenedEvent,
    ReceiveChannelSettledEvent,
    ReceiveMonitoringNewBalanceProofEvent,
    ReceiveMonitoringRewardClaimedEvent,
    ReceiveNonClosingBalanceProofUpdatedEvent,
)


@pytest.fixture(autouse=True)
def mock_first_allowed_block(monkeypatch):
    monkeypatch.setattr(
        "monitoring_service.handlers._first_allowed_block_to_monitor", Mock(return_value=1)
    )


def assert_channel_state(context: Context, state: ChannelState):
    channel = context.database.get_channel(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS, channel_id=DEFAULT_CHANNEL_IDENTIFIER
    )
    assert channel
    assert channel.state == state


def create_default_token_network(context: Context) -> None:
    context.database.conn.execute(
        "INSERT INTO token_network (address) VALUES (?)",
        [to_checksum_address(DEFAULT_TOKEN_NETWORK_ADDRESS)],
    )


def setup_state_with_open_channel(context: Context) -> Context:
    create_default_token_network(context)
    event = ReceiveChannelOpenedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        participant1=DEFAULT_PARTICIPANT1,
        participant2=DEFAULT_PARTICIPANT2,
        settle_timeout=DEFAULT_SETTLE_TIMEOUT,
        block_number=BlockNumber(42),
    )
    assert context.database.channel_count() == 0

    channel_opened_event_handler(event, context)

    return context


def setup_state_with_closed_channel(context: Context) -> Context:
    context = setup_state_with_open_channel(context)

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(52),
    )
    channel_closed_event_handler(event, context)

    assert context.database.channel_count() == 1
    assert_channel_state(context, ChannelState.CLOSED)

    return context


def get_scheduled_claim_event(database: Database) -> Optional[ScheduledEvent]:
    events = database.get_scheduled_events(max_trigger_block=BlockNumber(999_999))

    filtered_events = [
        event for event in events if isinstance(event.event, ActionClaimRewardTriggeredEvent)
    ]
    assert len(filtered_events) <= 1

    if len(filtered_events) == 0:
        return None

    return filtered_events[0]


@pytest.fixture
def context(ms_database: Database):
    return Context(
        ms_state=ms_database.load_state(),
        database=ms_database,
        web3=Web3Mock(),
        monitoring_service_contract=Mock(),
        user_deposit_contract=Mock(),
        min_reward=1,
        required_confirmations=1,
    )


def test_event_handler_ignore_other_events(context: Context):
    event = Event()

    for handler in [
        channel_opened_event_handler,
        channel_closed_event_handler,
        non_closing_balance_proof_updated_event_handler,
        channel_settled_event_handler,
        monitor_new_balance_proof_event_handler,
        monitor_reward_claim_event_handler,
        action_monitoring_triggered_event_handler,
        action_claim_reward_triggered_event_handler,
        updated_head_block_event_handler,
    ]:
        with pytest.raises(AssertionError):
            handler(event=event, context=context)


def test_channel_opened_event_handler_adds_channel(context: Context):
    create_default_token_network(context)
    event = ReceiveChannelOpenedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        participant1=DEFAULT_PARTICIPANT1,
        participant2=DEFAULT_PARTICIPANT2,
        settle_timeout=BlockTimeout(100),
        block_number=BlockNumber(42),
    )

    assert context.database.channel_count() == 0
    channel_opened_event_handler(event, context)

    assert context.database.channel_count() == 1
    assert_channel_state(context, ChannelState.OPENED)


def test_channel_closed_event_handler_closes_existing_channel(context: Context):
    context = setup_state_with_open_channel(context)
    context.web3.eth.blockNumber = BlockNumber(60)
    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(52),
    )
    channel_closed_event_handler(event, context)

    # ActionMonitoringTriggeredEvent has been triggered
    assert context.database.scheduled_event_count() == 1

    assert context.database.channel_count() == 1
    assert_channel_state(context, ChannelState.CLOSED)


def test_channel_closed_event_handler_idempotency(context: Context):
    context = setup_state_with_open_channel(context)
    context.web3.eth.blockNumber = BlockNumber(60)

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(52),
    )
    channel_closed_event_handler(event, context)

    # ActionMonitoringTriggeredEvent has been triggered
    assert context.database.scheduled_event_count() == 1
    assert context.database.channel_count() == 1
    assert_channel_state(context, ChannelState.CLOSED)

    # run handler again, check idempotency
    channel_closed_event_handler(event, context)
    assert context.database.scheduled_event_count() == 1


def test_channel_closed_event_handler_ignores_existing_channel_after_timeout(context: Context):
    context = setup_state_with_open_channel(context)
    context.web3.eth.blockNumber = BlockNumber(200)

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(52),
    )
    channel_closed_event_handler(event, context)

    # no ActionMonitoringTriggeredEvent has been triggered
    assert context.database.scheduled_event_count() == 0

    assert context.database.channel_count() == 1
    assert_channel_state(context, ChannelState.CLOSED)


def test_channel_closed_event_handler_leaves_existing_channel(context: Context):
    context = setup_state_with_open_channel(context)

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=ChannelID(4),
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(52),
    )
    channel_closed_event_handler(event, context)

    assert context.database.channel_count() == 1
    assert_channel_state(context, ChannelState.OPENED)


def test_channel_closed_event_handler_trigger_action_monitor_event_with_monitor_request(
    context: Context,
):
    context = setup_state_with_open_channel(context)
    # add MR to DB
    context.database.upsert_monitor_request(create_signed_monitor_request())

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(52),
    )

    channel_closed_event_handler(event, context)
    assert context.database.scheduled_event_count() == 1


def test_channel_closed_event_handler_trigger_action_monitor_event_without_monitor_request(
    context: Context,
):
    context = setup_state_with_open_channel(context)

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(52),
    )

    channel_closed_event_handler(event, context)
    assert context.database.scheduled_event_count() == 1


def test_channel_settled_event_handler_settles_existing_channel(context: Context):
    context = setup_state_with_closed_channel(context)

    event = ReceiveChannelSettledEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        block_number=BlockNumber(52),
    )
    channel_settled_event_handler(event, context)

    assert context.database.channel_count() == 1
    assert_channel_state(context, ChannelState.SETTLED)


def test_channel_settled_event_handler_leaves_existing_channel(context: Context):
    context = setup_state_with_closed_channel(context)

    event = ReceiveChannelSettledEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=ChannelID(4),
        block_number=BlockNumber(52),
    )
    channel_settled_event_handler(event, context)

    assert context.database.channel_count() == 1
    assert_channel_state(context, ChannelState.CLOSED)


def test_channel_bp_updated_event_handler_sets_update_status_if_not_set(context: Context):
    context = setup_state_with_closed_channel(context)

    event_bp = ReceiveNonClosingBalanceProofUpdatedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        nonce=Nonce(2),
        block_number=BlockNumber(23),
    )

    channel = context.database.get_channel(
        event_bp.token_network_address, event_bp.channel_identifier
    )
    assert channel
    assert channel.update_status is None

    non_closing_balance_proof_updated_event_handler(event_bp, context)

    assert context.database.channel_count() == 1
    channel = context.database.get_channel(
        event_bp.token_network_address, event_bp.channel_identifier
    )
    assert channel
    assert channel.update_status is not None
    assert channel.update_status.nonce == 2
    assert channel.update_status.update_sender_address == DEFAULT_PARTICIPANT1

    event_bp2 = ReceiveNonClosingBalanceProofUpdatedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        nonce=Nonce(5),
        block_number=BlockNumber(53),
    )

    non_closing_balance_proof_updated_event_handler(event_bp2, context)

    assert context.database.channel_count() == 1
    channel = context.database.get_channel(
        event_bp.token_network_address, event_bp.channel_identifier
    )
    assert channel
    assert channel.update_status is not None
    assert channel.update_status.nonce == 5
    assert channel.update_status.update_sender_address == DEFAULT_PARTICIPANT1


def test_monitor_new_balance_proof_event_handler_sets_update_status(context: Context):
    context = setup_state_with_closed_channel(context)

    new_balance_event = ReceiveMonitoringNewBalanceProofEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        reward_amount=TokenAmount(1),
        nonce=Nonce(2),
        ms_address=Address(bytes([4] * 20)),
        raiden_node_address=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(62),
    )

    channel = context.database.get_channel(
        new_balance_event.token_network_address, new_balance_event.channel_identifier
    )
    assert channel
    assert channel.update_status is None
    assert get_scheduled_claim_event(context.database) is None

    monitor_new_balance_proof_event_handler(new_balance_event, context)

    assert context.database.channel_count() == 1
    channel = context.database.get_channel(
        new_balance_event.token_network_address, new_balance_event.channel_identifier
    )
    assert channel
    assert channel.update_status is not None
    assert channel.update_status.nonce == 2
    assert channel.update_status.update_sender_address == bytes([4] * 20)

    scheduled_claim_event = get_scheduled_claim_event(context.database)
    assert scheduled_claim_event is not None
    assert scheduled_claim_event.trigger_block_number == 52 + 100 + 1

    new_balance_event2 = ReceiveMonitoringNewBalanceProofEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        reward_amount=TokenAmount(1),
        nonce=Nonce(5),
        ms_address=Address(bytes([4] * 20)),
        raiden_node_address=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(63),
    )

    monitor_new_balance_proof_event_handler(new_balance_event2, context)

    assert context.database.channel_count() == 1
    channel = context.database.get_channel(
        new_balance_event.token_network_address, new_balance_event.channel_identifier
    )
    assert channel
    assert channel.update_status is not None
    assert channel.update_status.nonce == 5
    assert channel.update_status.update_sender_address == bytes([4] * 20)

    scheduled_claim_event = get_scheduled_claim_event(context.database)
    assert scheduled_claim_event is not None
    assert scheduled_claim_event.trigger_block_number == 52 + 100 + 1


def test_monitor_new_balance_proof_event_handler_idempotency(context: Context):
    context = setup_state_with_closed_channel(context)

    new_balance_event = ReceiveMonitoringNewBalanceProofEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        reward_amount=TokenAmount(1),
        nonce=Nonce(2),
        ms_address=Address(bytes([3] * 20)),
        raiden_node_address=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(23),
    )

    channel = context.database.get_channel(
        new_balance_event.token_network_address, new_balance_event.channel_identifier
    )
    assert channel
    assert channel.update_status is None

    monitor_new_balance_proof_event_handler(new_balance_event, context)

    assert context.database.scheduled_event_count() == 1
    assert context.database.channel_count() == 1
    channel = context.database.get_channel(
        new_balance_event.token_network_address, new_balance_event.channel_identifier
    )
    assert channel
    assert channel.update_status is not None
    assert channel.update_status.nonce == 2
    assert channel.update_status.update_sender_address == bytes([3] * 20)

    monitor_new_balance_proof_event_handler(new_balance_event, context)

    assert context.database.scheduled_event_count() == 1
    assert context.database.channel_count() == 1
    channel = context.database.get_channel(
        new_balance_event.token_network_address, new_balance_event.channel_identifier
    )
    assert channel
    assert channel.update_status is not None
    assert channel.update_status.nonce == 2
    assert channel.update_status.update_sender_address == bytes([3] * 20)


def test_monitor_reward_claimed_event_handler(context: Context, log):
    context = setup_state_with_closed_channel(context)

    claim_event = ReceiveMonitoringRewardClaimedEvent(
        ms_address=context.ms_state.address,
        amount=TokenAmount(1),
        reward_identifier="REWARD",
        block_number=BlockNumber(23),
    )

    monitor_reward_claim_event_handler(claim_event, context)
    assert log.has("Successfully claimed reward")

    claim_event.ms_address = Address(bytes([3] * 20))
    monitor_reward_claim_event_handler(claim_event, context)
    assert log.has("Another MS claimed reward")


def test_action_monitoring_triggered_event_handler_does_not_trigger_monitor_call_when_nonce_to_small(  # noqa
    context: Context,
):
    context = setup_state_with_closed_channel(context)

    event3 = ReceiveMonitoringNewBalanceProofEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        reward_amount=TokenAmount(1),
        nonce=Nonce(5),
        ms_address=Address(bytes([3] * 20)),
        raiden_node_address=DEFAULT_PARTICIPANT2,
        block_number=BlockNumber(23),
    )

    channel = context.database.get_channel(event3.token_network_address, event3.channel_identifier)
    assert channel
    assert channel.update_status is None

    monitor_new_balance_proof_event_handler(event3, context)

    # add MR to DB, with nonce being smaller than in event3
    context.database.upsert_monitor_request(create_signed_monitor_request(nonce=Nonce(4)))

    event4 = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    channel = context.database.get_channel(event4.token_network_address, event4.channel_identifier)
    assert channel
    assert channel.update_status is not None
    assert channel.monitor_tx_hash is None

    action_monitoring_triggered_event_handler(event4, context)

    assert context.database.channel_count() == 1
    assert channel
    assert channel.monitor_tx_hash is None


def test_action_monitoring_rescheduling_when_user_lacks_funds(context: Context):
    reward_amount = TokenAmount(10)
    context = setup_state_with_closed_channel(context)
    context.database.upsert_monitor_request(
        create_signed_monitor_request(nonce=Nonce(6), reward_amount=reward_amount)
    )

    event = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )
    scheduled_events_before = context.database.get_scheduled_events(
        max_trigger_block=BlockNumber(10000)
    )

    # Try to call monitor when the user has insufficient funds
    with patch("monitoring_service.handlers.get_pessimistic_udc_balance", Mock(return_value=0)):
        action_monitoring_triggered_event_handler(event, context)
    assert not context.monitoring_service_contract.functions.monitor.called

    # Now the event must have been rescheduled
    # TODO: check that the event is rescheduled to trigger at the right block
    scheduled_events_after = context.database.get_scheduled_events(
        max_trigger_block=BlockNumber(10000)
    )
    new_events = set(scheduled_events_after) - set(scheduled_events_before)
    assert len(new_events) == 1
    assert new_events.pop().event == event

    # With sufficient funds it must succeed
    with patch(
        "monitoring_service.handlers.get_pessimistic_udc_balance",
        Mock(return_value=reward_amount * UDC_SECURITY_MARGIN_FACTOR_MS),
    ):
        action_monitoring_triggered_event_handler(event, context)
    assert context.monitoring_service_contract.functions.monitor.called


def test_action_monitoring_triggered_event_handler_with_sufficient_balance_does_trigger_monitor_call(  # noqa
    context: Context,
):
    """ Tests that `monitor` is called when the ActionMonitoringTriggeredEvent is triggered and
    user has sufficient balance in user deposit contract

    Also a test for https://github.com/raiden-network/raiden-services/issues/29 , as the MR
    is sent after the channel has been closed.
    """
    context = setup_state_with_closed_channel(context)

    context.database.upsert_monitor_request(
        create_signed_monitor_request(nonce=Nonce(6), reward_amount=TokenAmount(10))
    )

    trigger_event = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    channel = context.database.get_channel(
        trigger_event.token_network_address, trigger_event.channel_identifier
    )
    assert channel
    assert channel.monitor_tx_hash is None

    context.user_deposit_contract.functions.effectiveBalance(
        DEFAULT_PARTICIPANT2
    ).call.return_value = 21
    action_monitoring_triggered_event_handler(trigger_event, context)

    # check that the monitor call has been done
    assert context.monitoring_service_contract.functions.monitor.called is True


def test_action_monitoring_triggered_event_handler_with_insufficient_reward_amount_does_not_trigger_monitor_call(  # noqa
    context: Context,
):
    """ Tests that `monitor` is not called when the ActionMonitoringTriggeredEvent is triggered but
    the monitor request shows an insufficient reward amount
    """
    context = setup_state_with_closed_channel(context)

    context.database.upsert_monitor_request(
        create_signed_monitor_request(nonce=Nonce(6), reward_amount=TokenAmount(0))
    )

    trigger_event = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    channel = context.database.get_channel(
        trigger_event.token_network_address, trigger_event.channel_identifier
    )
    assert channel
    assert channel.monitor_tx_hash is None

    context.user_deposit_contract.functions.effectiveBalance(
        DEFAULT_PARTICIPANT2
    ).call.return_value = 21
    action_monitoring_triggered_event_handler(trigger_event, context)

    # check that the monitor call has been done
    assert context.monitoring_service_contract.functions.monitor.called is False


def test_action_monitoring_triggered_event_handler_without_sufficient_balance_doesnt_trigger_monitor_call(  # noqa
    context: Context,
):
    """ Tests that `monitor` is not called when user has insufficient balance in user deposit contract

    Also a test for https://github.com/raiden-network/raiden-services/issues/29 , as the MR
    is sent after the channel has been closed.
    """
    context = setup_state_with_closed_channel(context)

    context.database.upsert_monitor_request(
        create_signed_monitor_request(nonce=Nonce(6), reward_amount=TokenAmount(10))
    )

    trigger_event = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    channel = context.database.get_channel(
        trigger_event.token_network_address, trigger_event.channel_identifier
    )
    assert channel
    assert channel.monitor_tx_hash is None

    context.user_deposit_contract.functions.effectiveBalance(
        DEFAULT_PARTICIPANT2
    ).call.return_value = 0
    action_monitoring_triggered_event_handler(trigger_event, context)

    # check that the monitor call has been done
    assert context.monitoring_service_contract.functions.monitor.called is False


def test_mr_available_before_channel_triggers_monitor_call(context: Context):
    """ Tests that the MR is read from the DB, even if it is supplied before the channel was opened.

    See https://github.com/raiden-network/raiden-services/issues/26
    """

    # add MR to DB
    context.database.upsert_monitor_request(create_signed_monitor_request())

    context = setup_state_with_closed_channel(context)

    event = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    context.user_deposit_contract.functions.effectiveBalance(
        DEFAULT_PARTICIPANT2
    ).call.return_value = 100
    action_monitoring_triggered_event_handler(event, context)

    # check that the monitor call has been done
    assert context.monitoring_service_contract.functions.monitor.called is True


def test_mr_with_unknown_signatures(context: Context):
    """ The signatures are valid but don't belong to the participants.
    """
    context = setup_state_with_closed_channel(context)

    def assert_mr_is_ignored(mr):
        context.database.upsert_monitor_request(mr)

        event = ActionMonitoringTriggeredEvent(
            token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
            channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
            non_closing_participant=DEFAULT_PARTICIPANT2,
        )

        action_monitoring_triggered_event_handler(event, context)
        assert not context.monitoring_service_contract.functions.monitor.called

    assert_mr_is_ignored(create_signed_monitor_request(closing_privkey=get_random_privkey()))
    assert_mr_is_ignored(create_signed_monitor_request(nonclosing_privkey=get_random_privkey()))


def test_action_claim_reward_triggered_event_handler_does_trigger_claim_call(  # noqa
    context: Context,
):
    """ Tests that `claimReward` is called when the ActionMonitoringTriggeredEvent is triggered and
    user has sufficient balance in user deposit contract
    """
    context = setup_state_with_closed_channel(context)

    context.database.upsert_monitor_request(
        create_signed_monitor_request(nonce=Nonce(6), reward_amount=TokenAmount(10))
    )

    trigger_event = ActionClaimRewardTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    channel = context.database.get_channel(
        trigger_event.token_network_address, trigger_event.channel_identifier
    )
    assert channel
    assert channel.claim_tx_hash is None

    # Set update state
    channel.update_status = OnChainUpdateStatus(
        update_sender_address=context.ms_state.address, nonce=Nonce(6)
    )
    context.database.upsert_channel(channel)

    action_claim_reward_triggered_event_handler(trigger_event, context)

    # check that the monitor call has been done
    assert context.monitoring_service_contract.functions.claimReward.called is True


def test_action_claim_reward_triggered_event_handler_without_reward_doesnt_trigger_claim_call(  # noqa
    context: Context,
):
    """ Tests that `claimReward` is called when the ActionMonitoringTriggeredEvent is triggered and
    user has sufficient balance in user deposit contract
    """
    context = setup_state_with_closed_channel(context)

    context.database.upsert_monitor_request(
        create_signed_monitor_request(nonce=Nonce(6), reward_amount=TokenAmount(0))
    )

    trigger_event = ActionClaimRewardTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    channel = context.database.get_channel(
        trigger_event.token_network_address, trigger_event.channel_identifier
    )
    assert channel
    assert channel.claim_tx_hash is None

    # Set update state
    channel.update_status = OnChainUpdateStatus(
        update_sender_address=context.ms_state.address, nonce=Nonce(6)
    )
    context.database.upsert_channel(channel)

    action_claim_reward_triggered_event_handler(trigger_event, context)

    # check that the monitor call has been done
    assert context.monitoring_service_contract.functions.claimReward.called is False


def test_action_claim_reward_triggered_event_handler_without_update_state_doesnt_trigger_claim_call(  # noqa
    context: Context,
):
    """ Tests that `claimReward` is called when the ActionMonitoringTriggeredEvent is triggered and
    user has sufficient balance in user deposit contract
    """
    context = setup_state_with_closed_channel(context)

    context.database.upsert_monitor_request(
        create_signed_monitor_request(nonce=Nonce(6), reward_amount=TokenAmount(0))
    )

    trigger_event = ActionClaimRewardTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    channel = context.database.get_channel(
        trigger_event.token_network_address, trigger_event.channel_identifier
    )
    assert channel
    assert channel.claim_tx_hash is None

    # Set update state
    channel.update_status = OnChainUpdateStatus(
        update_sender_address=Address(bytes([1] * 20)), nonce=Nonce(6)
    )
    context.database.upsert_channel(channel)

    action_claim_reward_triggered_event_handler(trigger_event, context)

    # check that the monitor call has been done
    assert context.monitoring_service_contract.functions.claimReward.called is False

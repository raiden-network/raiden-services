from unittest.mock import Mock

import pytest
from eth_utils import encode_hex

from monitoring_service.events import (
    ActionMonitoringTriggeredEvent,
    Event,
    ReceiveChannelClosedEvent,
    ReceiveChannelOpenedEvent,
    ReceiveChannelSettledEvent,
    ReceiveMonitoringNewBalanceProofEvent,
    ReceiveNonClosingBalanceProofUpdatedEvent,
)
from monitoring_service.handlers import (
    Context,
    action_claim_reward_triggered_event_handler,
    action_monitoring_triggered_event_handler,
    channel_closed_event_handler,
    channel_non_closing_balance_proof_updated_event_handler,
    channel_opened_event_handler,
    channel_settled_event_handler,
    monitor_new_balance_proof_event_handler,
    monitor_reward_claim_event_handler,
    updated_head_block_event_handler,
)
from monitoring_service.states import MonitorRequest
from raiden_contracts.constants import ChannelState
from raiden_libs.utils import eth_sign, private_key_to_address

DEFAULT_TOKEN_NETWORK_ADDRESS = '0x0000000000000000000000000000000000000000'
DEFAULT_CHANNEL_IDENTIFIER = 3
DEFAULT_PRIVATE_KEY1 = '0x' + '1' * 64
DEFAULT_PRIVATE_KEY2 = '0x' + '2' * 64
DEFAULT_PARTICIPANT1 = private_key_to_address(DEFAULT_PRIVATE_KEY1)
DEFAULT_PARTICIPANT2 = private_key_to_address(DEFAULT_PRIVATE_KEY2)
DEFAULT_SETTLE_TIMEOUT = 100


def assert_channel_state(context, state):
    channel = context.db.get_channel(
        DEFAULT_TOKEN_NETWORK_ADDRESS,
        DEFAULT_CHANNEL_IDENTIFIER,
    )
    assert channel
    assert channel.state == state


def setup_state_with_open_channel(context: Context) -> Context:
    create_default_token_network(context)
    event = ReceiveChannelOpenedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        participant1=DEFAULT_PARTICIPANT1,
        participant2=DEFAULT_PARTICIPANT2,
        settle_timeout=DEFAULT_SETTLE_TIMEOUT,
        block_number=42,
    )
    assert context.db.channel_count() == 0

    channel_opened_event_handler(event, context)

    return context


def setup_state_with_closed_channel(context: Context) -> Context:
    context = setup_state_with_open_channel(context)

    event2 = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=52,
    )
    channel_closed_event_handler(event2, context)

    assert context.db.channel_count() == 1
    assert_channel_state(context, ChannelState.CLOSED)

    return context


def get_signed_monitor_request(nonce: int = 5) -> MonitorRequest:
    monitor_request = MonitorRequest(
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        chain_id=1,
        balance_hash='',
        nonce=nonce,
        additional_hash='',
        closing_signature='',
        non_closing_signature='',
        reward_amount=0,
        reward_proof_signature='',
    )
    monitor_request.closing_signature = encode_hex(
        eth_sign(DEFAULT_PRIVATE_KEY1, monitor_request.packed_balance_proof_data()),
    )
    monitor_request.non_closing_signature = encode_hex(
        eth_sign(DEFAULT_PRIVATE_KEY2, monitor_request.packed_non_closing_data()),
    )
    monitor_request.reward_proof_signature = encode_hex(
        eth_sign(DEFAULT_PRIVATE_KEY2, monitor_request.packed_reward_proof_data()),
    )
    return monitor_request


@pytest.fixture
def context(ms_database):
    return Context(
        ms_state=ms_database.load_state(sync_start_block=0),
        db=ms_database,
        scheduled_events=[],
        w3=Mock(),
        contract_manager=Mock(),
        last_known_block=0,
        monitoring_service_contract=Mock(),
    )


def create_default_token_network(context):
    context.db.conn.execute(
        "INSERT INTO token_network (address) VALUES (?)",
        [DEFAULT_TOKEN_NETWORK_ADDRESS],
    )


def test_event_handler_ignore_other_events(
    context: Context,
):
    event = Event()

    for handler in [
        channel_opened_event_handler,
        channel_closed_event_handler,
        channel_non_closing_balance_proof_updated_event_handler,
        channel_settled_event_handler,
        monitor_new_balance_proof_event_handler,
        monitor_reward_claim_event_handler,
        action_monitoring_triggered_event_handler,
        action_claim_reward_triggered_event_handler,
        updated_head_block_event_handler,
    ]:
        with pytest.raises(AssertionError):
            handler(
                event=event,
                context=context,
            )


def test_channel_opened_event_handler_adds_channel(
    context: Context,
):
    create_default_token_network(context)
    event = ReceiveChannelOpenedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        participant1=DEFAULT_PARTICIPANT1,
        participant2=DEFAULT_PARTICIPANT2,
        settle_timeout=100,
        block_number=42,
    )

    assert context.db.channel_count() == 0
    channel_opened_event_handler(event, context)

    assert context.db.channel_count() == 1
    assert_channel_state(context, ChannelState.OPENED)


def test_channel_closed_event_handler_closes_existing_channel(
    context: Context,
):
    context = setup_state_with_open_channel(context)
    context.last_known_block = 60

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=52,
    )
    channel_closed_event_handler(event, context)

    # ActionMonitoringTriggeredEvent has been triggered
    assert len(context.scheduled_events) == 1

    assert context.db.channel_count() == 1
    assert_channel_state(context, ChannelState.CLOSED)


def test_channel_closed_event_handler_ignores_existing_channel_after_timeout(
    context: Context,
):
    context = setup_state_with_open_channel(context)
    context.last_known_block = 200

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=52,
    )
    channel_closed_event_handler(event, context)

    # no ActionMonitoringTriggeredEvent has been triggered
    assert len(context.scheduled_events) == 0

    assert context.db.channel_count() == 1
    assert_channel_state(context, ChannelState.CLOSED)


def test_channel_closed_event_handler_leaves_existing_channel(
    context: Context,
):
    context = setup_state_with_open_channel(context)

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=4,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=52,
    )
    channel_closed_event_handler(event, context)

    assert context.db.channel_count() == 1
    assert_channel_state(context, ChannelState.OPENED)


def test_channel_closed_event_handler_trigger_action_monitor_event_with_monitor_request(
    context: Context,
):
    context = setup_state_with_open_channel(context)
    # add MR to DB
    context.db.upsert_monitor_request(get_signed_monitor_request())

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=52,
    )

    channel_closed_event_handler(event, context)
    assert len(context.scheduled_events) == 1


def test_channel_closed_event_handler_trigger_action_monitor_event_without_monitor_request(
    context: Context,
):
    context = setup_state_with_open_channel(context)

    event = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=52,
    )

    channel_closed_event_handler(event, context)
    assert len(context.scheduled_events) == 1


def test_channel_settled_event_handler_settles_existing_channel(
    context: Context,
):
    context = setup_state_with_closed_channel(context)

    event = ReceiveChannelSettledEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        block_number=52,
    )
    channel_settled_event_handler(event, context)

    assert context.db.channel_count() == 1
    assert_channel_state(context, ChannelState.SETTLED)


def test_channel_settled_event_handler_leaves_existing_channel(
    context: Context,
):
    context = setup_state_with_closed_channel(context)

    event = ReceiveChannelSettledEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=4,
        block_number=52,
    )
    channel_settled_event_handler(event, context)

    assert context.db.channel_count() == 1
    assert_channel_state(context, ChannelState.CLOSED)


def test_channel_bp_updated_event_handler_sets_update_status_if_not_set(
    context: Context,
):
    context = setup_state_with_closed_channel(context)

    event_bp = ReceiveNonClosingBalanceProofUpdatedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        nonce=2,
        block_number=23,
    )

    channel = context.db.get_channel(event_bp.token_network_address, event_bp.channel_identifier)
    assert channel
    assert channel.update_status is None

    channel_non_closing_balance_proof_updated_event_handler(event_bp, context)

    assert context.db.channel_count() == 1
    channel = context.db.get_channel(event_bp.token_network_address, event_bp.channel_identifier)
    assert channel
    assert channel.update_status is not None
    assert channel.update_status.nonce == 2
    assert channel.update_status.update_sender_address == DEFAULT_PARTICIPANT1

    event_bp2 = ReceiveNonClosingBalanceProofUpdatedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        nonce=5,
        block_number=53,
    )

    channel_non_closing_balance_proof_updated_event_handler(event_bp2, context)

    assert context.db.channel_count() == 1
    channel = context.db.get_channel(event_bp.token_network_address, event_bp.channel_identifier)
    assert channel
    assert channel.update_status is not None
    assert channel.update_status.nonce == 5
    assert channel.update_status.update_sender_address == DEFAULT_PARTICIPANT1


def test_monitor_new_balance_proof_event_handler_sets_update_status(
    context: Context,
):
    context = setup_state_with_closed_channel(context)

    event3 = ReceiveMonitoringNewBalanceProofEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        reward_amount=1,
        nonce=2,
        ms_address='C',
        raiden_node_address=DEFAULT_PARTICIPANT2,
        block_number=23,
    )

    channel = context.db.get_channel(event3.token_network_address, event3.channel_identifier)
    assert channel
    assert channel.update_status is None

    monitor_new_balance_proof_event_handler(event3, context)

    assert context.db.channel_count() == 1
    channel = context.db.get_channel(event3.token_network_address, event3.channel_identifier)
    assert channel
    assert channel.update_status is not None
    assert channel.update_status.nonce == 2
    assert channel.update_status.update_sender_address == 'C'

    event4 = ReceiveMonitoringNewBalanceProofEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        reward_amount=1,
        nonce=5,
        ms_address='D',
        raiden_node_address=DEFAULT_PARTICIPANT2,
        block_number=23,
    )

    monitor_new_balance_proof_event_handler(event4, context)

    assert context.db.channel_count() == 1
    channel = context.db.get_channel(event3.token_network_address, event3.channel_identifier)
    assert channel
    assert channel.update_status is not None
    assert channel.update_status.nonce == 5
    assert channel.update_status.update_sender_address == 'D'


def test_action_monitoring_triggered_event_handler_does_not_trigger_monitor_call_when_nonce_to_small(  # noqa
    context: Context,
):
    context = setup_state_with_closed_channel(context)

    event3 = ReceiveMonitoringNewBalanceProofEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        reward_amount=1,
        nonce=5,
        ms_address='C',
        raiden_node_address=DEFAULT_PARTICIPANT2,
        block_number=23,
    )

    channel = context.db.get_channel(event3.token_network_address, event3.channel_identifier)
    assert channel
    assert channel.update_status is None

    monitor_new_balance_proof_event_handler(event3, context)

    # add MR to DB, with nonce being smaller than in event3
    context.db.upsert_monitor_request(get_signed_monitor_request(nonce=4))

    event4 = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    channel = context.db.get_channel(event4.token_network_address, event4.channel_identifier)
    assert channel
    assert channel.update_status is not None
    assert channel.closing_tx_hash is None

    action_monitoring_triggered_event_handler(event4, context)

    assert context.db.channel_count() == 1
    assert channel
    assert channel.closing_tx_hash is None


def test_action_monitoring_triggered_event_handler_does_trigger_monitor_call(  # noqa
    context: Context,
):
    """ Tests that `monitor` is called when the ActionMonitoringTriggeredEvent is triggered

    Also a test for https://github.com/raiden-network/raiden-services/issues/29 , as the MR
    is sent after the channel has been closed.
    """
    context = setup_state_with_closed_channel(context)

    event_new_bp = ReceiveMonitoringNewBalanceProofEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        reward_amount=1,
        nonce=5,
        ms_address='C',
        raiden_node_address=DEFAULT_PARTICIPANT2,
        block_number=23,
    )

    channel = context.db.get_channel(
        event_new_bp.token_network_address,
        event_new_bp.channel_identifier,
    )
    assert channel
    assert channel.update_status is None

    monitor_new_balance_proof_event_handler(event_new_bp, context)

    # add MR to DB, with nonce being larger than in event_new_bp
    context.db.upsert_monitor_request(get_signed_monitor_request(nonce=6))

    event4 = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    channel = context.db.get_channel(event4.token_network_address, event4.channel_identifier)
    assert channel
    assert channel.update_status is not None
    assert channel.closing_tx_hash is None

    action_monitoring_triggered_event_handler(event4, context)

    # check that the monitor call has been done
    assert context.monitoring_service_contract.functions.monitor.called is True


def test_mr_available_before_channel_triggers_monitor_call(
    context: Context,
):
    """ Tests that the MR is read from the DB, even if it is supplied before the channel was opened.

    See https://github.com/raiden-network/raiden-services/issues/26
    """

    # add MR to DB
    context.db.upsert_monitor_request(get_signed_monitor_request())

    context = setup_state_with_closed_channel(context)

    event = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        non_closing_participant=DEFAULT_PARTICIPANT2,
    )

    action_monitoring_triggered_event_handler(event, context)

    # check that the monitor call has been done
    assert context.monitoring_service_contract.functions.monitor.called is True

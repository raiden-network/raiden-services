from unittest.mock import Mock

import pytest

from monitoring_service.database import Database
from monitoring_service.events import (
    Event,
    ReceiveChannelClosedEvent,
    ReceiveChannelOpenedEvent,
    ReceiveNonClosingBalanceProofUpdatedEvent,
    ReceiveMonitoringNewBalanceProofEvent,
    ActionMonitoringTriggeredEvent,
)
from monitoring_service.handlers import (
    Context,
    channel_closed_event_handler,
    channel_opened_event_handler,
    channel_non_closing_balance_proof_updated_event_handler,
    channel_settled_event_handler,
    monitor_new_balance_proof_event_handler,
    monitor_reward_claim_event_handler,
    action_monitoring_triggered_event_handler,
    action_claim_reward_triggered_event_handler,
    updated_head_block_event_handler,
)
from monitoring_service.states import BlockchainState, MonitoringServiceState, MonitorRequest
from raiden_contracts.constants import ChannelState

DEFAULT_TOKEN_NETWORK_ADDRESS = '0x0000000000000000000000000000000000000000'
DEFAULT_CHANNEL_IDENTIFIER = 3
DEFAULT_PARTICIPANT1 = '0x1111111111111111111111111111111111111111'
DEFAULT_PARTICIPANT2 = '0x2222222222222222222222222222222222222222'
DEFAULT_SETTLE_TIMEOUT = 100


def setup_state_with_closed_channel(context: Context) -> Context:
    event = ReceiveChannelOpenedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        participant1=DEFAULT_PARTICIPANT1,
        participant2=DEFAULT_PARTICIPANT2,
        settle_timeout=DEFAULT_SETTLE_TIMEOUT,
        block_number=42,
    )
    assert len(context.db.channels) == 0

    channel_opened_event_handler(event, context)

    assert len(context.db.channels) == 1
    assert context.db.channels[0].state == ChannelState.OPENED

    event2 = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=52,
    )
    channel_closed_event_handler(event2, context)

    assert len(context.db.channels) == 1
    assert context.db.channels[0].state == ChannelState.CLOSED

    return context


@pytest.fixture
def context():
    return Context(
        ms_state=MonitoringServiceState(
            blockchain_state=BlockchainState(
                token_network_registry_address='',
                monitor_contract_address='',
                latest_known_block=0,
                token_network_addresses=[],
            ),
            address='',
        ),
        db=Database(),
        scheduled_events=[],
        w3=Mock(),
        contract_manager=Mock(),
        last_known_block=0,
        monitoring_service_contract=Mock()
    )


def test_event_handler_ignore_other_events(
    context: Context,
):
    event = Event()

    with pytest.raises(AssertionError):
        channel_opened_event_handler(
            event=event,
            context=context,
        )

    with pytest.raises(AssertionError):
        channel_closed_event_handler(
            event=event,
            context=context,
        )

    with pytest.raises(AssertionError):
        channel_non_closing_balance_proof_updated_event_handler(
            event=event,
            context=context,
        )

    with pytest.raises(AssertionError):
        channel_settled_event_handler(
            event=event,
            context=context,
        )

    with pytest.raises(AssertionError):
        monitor_new_balance_proof_event_handler(
            event=event,
            context=context,
        )

    with pytest.raises(AssertionError):
        monitor_reward_claim_event_handler(
            event=event,
            context=context,
        )

    with pytest.raises(AssertionError):
        action_monitoring_triggered_event_handler(
            event=event,
            context=context,
        )

    with pytest.raises(AssertionError):
        action_claim_reward_triggered_event_handler(
            event=event,
            context=context,
        )

    with pytest.raises(AssertionError):
        updated_head_block_event_handler(
            event=event,
            context=context,
        )


def test_channel_opened_event_handler_adds_channel(
    context: Context,
):
    event = ReceiveChannelOpenedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        participant1=DEFAULT_PARTICIPANT1,
        participant2=DEFAULT_PARTICIPANT2,
        settle_timeout=100,
        block_number=42,
    )

    assert len(context.db.channels) == 0
    channel_opened_event_handler(event, context)

    assert len(context.db.channels) == 1


def test_channel_closed_event_handler_closes_existing_channel(
    context: Context,
):
    event = ReceiveChannelOpenedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        participant1=DEFAULT_PARTICIPANT1,
        participant2=DEFAULT_PARTICIPANT2,
        settle_timeout=100,
        block_number=42,
    )

    assert len(context.db.channels) == 0
    channel_opened_event_handler(event, context)

    assert len(context.db.channels) == 1
    assert context.db.channels[0].state == ChannelState.OPENED

    event2 = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=52,
    )
    channel_closed_event_handler(event2, context)

    assert len(context.db.channels) == 1
    assert context.db.channels[0].state == ChannelState.CLOSED


def test_channel_closed_event_handler_leaves_existing_channel(
    context: Context,
):
    event = ReceiveChannelOpenedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=3,
        participant1=DEFAULT_PARTICIPANT1,
        participant2=DEFAULT_PARTICIPANT2,
        settle_timeout=100,
        block_number=42,
    )

    assert len(context.db.channels) == 0
    channel_opened_event_handler(event, context)

    assert len(context.db.channels) == 1
    assert context.db.channels[0].state == ChannelState.OPENED

    event2 = ReceiveChannelClosedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=4,
        closing_participant=DEFAULT_PARTICIPANT2,
        block_number=52,
    )
    channel_closed_event_handler(event2, context)

    assert len(context.db.channels) == 1
    assert context.db.channels[0].state == ChannelState.OPENED


def test_channel_bp_updated_event_handler_sets_update_status_if_not_set(
    context: Context,
):
    context = setup_state_with_closed_channel(context)

    event3 = ReceiveNonClosingBalanceProofUpdatedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        nonce=2,
        block_number=23,
    )

    channel = context.db.get_channel(event3.token_network_address, event3.channel_identifier)
    assert channel.update_status is None

    channel_non_closing_balance_proof_updated_event_handler(event3, context)

    assert len(context.db.channels) == 1
    channel = context.db.get_channel(event3.token_network_address, event3.channel_identifier)
    assert channel.update_status is not None
    assert channel.update_status.nonce == 2
    assert channel.update_status.update_sender_address == DEFAULT_PARTICIPANT1

    event4 = ReceiveNonClosingBalanceProofUpdatedEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        closing_participant=DEFAULT_PARTICIPANT2,
        nonce=5,
        block_number=53,
    )

    channel_non_closing_balance_proof_updated_event_handler(event4, context)

    assert len(context.db.channels) == 1
    channel = context.db.get_channel(event3.token_network_address, event3.channel_identifier)
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
    assert channel.update_status is None

    monitor_new_balance_proof_event_handler(event3, context)

    assert len(context.db.channels) == 1
    channel = context.db.get_channel(event3.token_network_address, event3.channel_identifier)
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

    assert len(context.db.channels) == 1
    channel = context.db.get_channel(event3.token_network_address, event3.channel_identifier)
    assert channel.update_status is not None
    assert channel.update_status.nonce == 5
    assert channel.update_status.update_sender_address == 'D'


def test_action_monitoring_triggered_event_handler_does_not_trigger_monitor_call_when_nonce_to_small(
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
    assert channel.update_status is None

    monitor_new_balance_proof_event_handler(event3, context)

    # add MR to DB
    context.db.monitor_requests.append(MonitorRequest(
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        chain_id=1,
        balance_hash='',
        nonce=5,
        additional_hash='',
        closing_signature='',
        non_closing_signature='',
        reward_amount=0,
        reward_proof_signature='',
    ))

    event4 = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=DEFAULT_CHANNEL_IDENTIFIER,
    )

    channel = context.db.get_channel(event4.token_network_address, event4.channel_identifier)
    assert channel.update_status is not None
    assert channel.closing_tx_hash is None

    action_monitoring_triggered_event_handler(event4, context)

    assert len(context.db.channels) == 1
    assert channel.closing_tx_hash is None

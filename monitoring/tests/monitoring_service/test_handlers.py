from unittest.mock import Mock

import pytest

from monitoring_service.database import Database
from monitoring_service.events import Event, ReceiveChannelClosedEvent, ReceiveChannelOpenedEvent
from monitoring_service.handlers import (
    Context,
    channel_closed_event_handler,
    channel_opened_event_handler,
)
from monitoring_service.states import BlockchainState, MonitoringServiceState
from raiden_contracts.constants import ChannelState


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
        ),
        db=Database(),
        scheduled_events=[],
        w3=Mock(),
        contract_manager=Mock(),
        last_known_block=0,
    )


def test_channel_opened_event_handler_ignores_other_event(
    context: Context,
):
    event = Event()

    with pytest.raises(AssertionError):
        channel_opened_event_handler(
            event=event,
            context=context,
        )


def test_channel_opened_event_handler_adds_channel(
    context: Context,
):
    event = ReceiveChannelOpenedEvent(
        token_network_address='abc',
        channel_identifier=3,
        participant1='A',
        participant2='B',
        settle_timeout=100,
        block_number=42,
    )

    assert len(context.db.channels) == 0
    channel_opened_event_handler(event, context)

    assert len(context.db.channels) == 1


def test_channel_closed_event_handler_ignores_other_event(
    context: Context,
):
    event = Event()

    with pytest.raises(AssertionError):
        channel_closed_event_handler(
            event=event,
            context=context,
        )


def test_channel_closed_event_handler_closes_existing_channel(
    context: Context,
):
    event = ReceiveChannelOpenedEvent(
        token_network_address='abc',
        channel_identifier=3,
        participant1='A',
        participant2='B',
        settle_timeout=100,
        block_number=42,
    )

    assert len(context.db.channels) == 0
    channel_opened_event_handler(event, context)

    assert len(context.db.channels) == 1
    assert context.db.channels[0].state == ChannelState.OPENED

    event2 = ReceiveChannelClosedEvent(
        token_network_address='abc',
        channel_identifier=3,
        closing_participant='B',
        block_number=52,
    )
    channel_closed_event_handler(event2, context)

    assert len(context.db.channels) == 1
    assert context.db.channels[0].state == ChannelState.CLOSED


def test_channel_closed_event_handler_leaves_existing_channel(
    context: Context,
):
    event = ReceiveChannelOpenedEvent(
        token_network_address='abc',
        channel_identifier=3,
        participant1='A',
        participant2='B',
        settle_timeout=100,
        block_number=42,
    )

    assert len(context.db.channels) == 0
    channel_opened_event_handler(event, context)

    assert len(context.db.channels) == 1
    assert context.db.channels[0].state == ChannelState.OPENED

    event2 = ReceiveChannelClosedEvent(
        token_network_address='abc',
        channel_identifier=4,
        closing_participant='B',
        block_number=52,
    )
    channel_closed_event_handler(event2, context)

    assert len(context.db.channels) == 1
    assert context.db.channels[0].state == ChannelState.OPENED

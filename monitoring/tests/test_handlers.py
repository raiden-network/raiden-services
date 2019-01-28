from unittest.mock import Mock

import pytest

from monitoring_service.events import Event, ReceiveTokenNetworkCreatedEvent
from monitoring_service.handlers import Context, TokenNetworkCreatedEventHandler
from monitoring_service.states import MonitoringServiceState


@pytest.fixture()
def context():
    return Context(
        ms_state=MonitoringServiceState(
            token_network_registry_address='',
            monitor_contract_address='',
            latest_known_block=0,
            token_network_addresses=[],
        ),
        db=Mock(),
        scheduled_events=[],
        w3=Mock(),
        contract_manager=Mock(),
        last_known_block=0,
    )


@pytest.fixture()
def token_network_created_event_handler(context):
    return TokenNetworkCreatedEventHandler(context)


def test_network_created_event_adds_network_address(
    context: Context,
    token_network_created_event_handler: TokenNetworkCreatedEventHandler,
):
    event = ReceiveTokenNetworkCreatedEvent(
        token_network_address='abc',
    )

    token_network_created_event_handler.handle_event(
        event=event,
    )

    assert context.ms_state.token_network_addresses == ['abc']


def test_tnceh_ignores_other_event(
    context: Context,
    token_network_created_event_handler: TokenNetworkCreatedEventHandler,
):
    event = Event()

    token_network_created_event_handler.handle_event(
        event=event,
    )

    assert context.ms_state.token_network_addresses == []

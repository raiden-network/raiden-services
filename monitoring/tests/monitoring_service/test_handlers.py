from unittest.mock import Mock

import pytest

from monitoring_service.events import Event
from monitoring_service.handlers import Context, channel_opened_event_handler
from monitoring_service.states import BlockchainState, MonitoringServiceState


@pytest.fixture()
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
        db=Mock(),
        scheduled_events=[],
        w3=Mock(),
        contract_manager=Mock(),
        last_known_block=0,
    )


def test_token_network_created_event_handler_ignores_other_event(
    context: Context,
):
    event = Event()

    with pytest.raises(AssertionError):
        channel_opened_event_handler(
            event=event,
            context=context,
        )

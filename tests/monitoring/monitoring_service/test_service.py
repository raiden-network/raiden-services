from typing import Callable
from unittest.mock import Mock, patch

from raiden_common.tests.utils.factories import (
    make_address,
    make_channel_identifier,
    make_transaction_hash,
)
from raiden_common.utils.typing import Timestamp
from web3 import Web3

from monitoring_service.events import ActionMonitoringTriggeredEvent, ScheduledEvent
from monitoring_service.service import MonitoringService
from raiden_libs.utils import get_posix_utc_time_now
from tests.monitoring.monitoring_service.factories import DEFAULT_TOKEN_NETWORK_ADDRESS
from tests.monitoring.monitoring_service.test_handlers import create_default_token_network


def test_check_pending_transactions(
    web3: Web3, wait_for_blocks: Callable[[int], None], monitoring_service: MonitoringService
):
    monitoring_service.context.required_confirmations = 3
    monitoring_service.database.add_waiting_transaction(waiting_tx_hash=make_transaction_hash())

    for tx_status in (0, 1):
        tx_receipt = {"blockNumber": web3.eth.block_number, "status": tx_status}
        with patch.object(
            web3.eth, "get_transaction_receipt", Mock(return_value=tx_receipt)
        ), patch.object(monitoring_service.database, "remove_waiting_transaction") as remove_mock:
            for should_call in (False, False, False, True):
                monitoring_service._check_pending_transactions()  # pylint: disable=protected-access # noqa

                assert remove_mock.called == should_call
                wait_for_blocks(1)


def test_trigger_scheduled_events(monitoring_service: MonitoringService):
    monitoring_service.context.required_confirmations = 5

    create_default_token_network(monitoring_service.context)

    triggered_event = ActionMonitoringTriggeredEvent(
        token_network_address=DEFAULT_TOKEN_NETWORK_ADDRESS,
        channel_identifier=make_channel_identifier(),
        non_closing_participant=make_address(),
    )

    trigger_timestamp = Timestamp(get_posix_utc_time_now())

    assert len(monitoring_service.database.get_scheduled_events(trigger_timestamp)) == 0
    monitoring_service.context.database.upsert_scheduled_event(
        ScheduledEvent(trigger_timestamp=trigger_timestamp, event=triggered_event)
    )
    assert len(monitoring_service.database.get_scheduled_events(trigger_timestamp)) == 1

    # Now run `_trigger_scheduled_events` and see if the event is removed
    monitoring_service._trigger_scheduled_events()  # pylint: disable=protected-access
    assert len(monitoring_service.database.get_scheduled_events(trigger_timestamp)) == 0

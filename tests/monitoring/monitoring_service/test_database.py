import random

from eth_utils import to_checksum_address
from tests.monitoring.monitoring_service.factories import (
    DEFAULT_TOKEN_NETWORK_ADDRESS,
    create_channel,
    create_signed_monitor_request,
)

from monitoring_service.database import Database
from monitoring_service.events import ActionMonitoringTriggeredEvent, ScheduledEvent
from monitoring_service.states import OnChainUpdateStatus
from raiden.constants import UINT256_MAX
from raiden.utils.typing import (
    Address,
    BlockNumber,
    ChannelID,
    TokenNetworkAddress,
    TransactionHash,
)


def test_scheduled_events(ms_database: Database):
    # Add token network used as foreign key
    token_network_address = TokenNetworkAddress(bytes([1] * 20))
    ms_database.conn.execute(
        "INSERT INTO token_network(address) VALUES (?)",
        [to_checksum_address(token_network_address)],
    )

    event1 = ScheduledEvent(
        trigger_block_number=BlockNumber(23),
        event=ActionMonitoringTriggeredEvent(
            token_network_address=token_network_address,
            channel_identifier=ChannelID(1),
            non_closing_participant=Address(bytes([1] * 20)),
        ),
    )

    assert ms_database.scheduled_event_count() == 0
    ms_database.upsert_scheduled_event(event=event1)
    assert ms_database.scheduled_event_count() == 1

    event2 = ScheduledEvent(
        trigger_block_number=BlockNumber(24),
        event=ActionMonitoringTriggeredEvent(
            token_network_address=token_network_address,
            channel_identifier=ChannelID(1),
            non_closing_participant=Address(bytes([1] * 20)),
        ),
    )

    ms_database.upsert_scheduled_event(event2)
    assert ms_database.scheduled_event_count() == 2

    assert len(ms_database.get_scheduled_events(BlockNumber(22))) == 0
    assert len(ms_database.get_scheduled_events(BlockNumber(23))) == 1
    assert len(ms_database.get_scheduled_events(BlockNumber(24))) == 2

    ms_database.upsert_scheduled_event(event1)
    assert ms_database.scheduled_event_count() == 2

    assert len(ms_database.get_scheduled_events(BlockNumber(22))) == 0
    assert len(ms_database.get_scheduled_events(BlockNumber(23))) == 1
    assert len(ms_database.get_scheduled_events(BlockNumber(24))) == 2

    ms_database.remove_scheduled_event(event2)
    assert len(ms_database.get_scheduled_events(BlockNumber(22))) == 0
    assert len(ms_database.get_scheduled_events(BlockNumber(23))) == 1
    assert len(ms_database.get_scheduled_events(BlockNumber(24))) == 1


def test_waiting_transactions(ms_database: Database):
    assert ms_database.get_waiting_transactions() == []

    ms_database.add_waiting_transaction(TransactionHash(b"A"))
    assert ms_database.get_waiting_transactions() == [b"A"]

    ms_database.add_waiting_transaction(TransactionHash(b"B"))
    assert ms_database.get_waiting_transactions() == [b"A", b"B"]

    ms_database.remove_waiting_transaction(TransactionHash(b"A"))
    assert ms_database.get_waiting_transactions() == [b"B"]


def test_save_and_load_monitor_request(ms_database: Database):
    request = create_signed_monitor_request()
    ms_database.upsert_monitor_request(request)

    restored = ms_database.get_monitor_request(
        token_network_address=request.token_network_address,
        channel_id=request.channel_identifier,
        non_closing_signer=request.non_closing_signer,
    )

    assert request == restored


def test_save_and_load_channel(ms_database: Database):
    ms_database.conn.execute(
        "INSERT INTO token_network (address) VALUES (?)",
        [to_checksum_address(DEFAULT_TOKEN_NETWORK_ADDRESS)],
    )
    for update_status in [
        None,
        OnChainUpdateStatus(
            update_sender_address=Address(bytes([1] * 20)), nonce=random.randint(0, UINT256_MAX)
        ),
    ]:
        channel = create_channel(update_status)
        ms_database.upsert_channel(channel)
        loaded_channel = ms_database.get_channel(
            token_network_address=channel.token_network_address, channel_id=channel.identifier
        )
        assert loaded_channel == channel

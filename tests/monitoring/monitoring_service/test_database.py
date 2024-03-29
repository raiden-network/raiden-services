import random
from datetime import datetime, timedelta

from raiden_common.constants import UINT256_MAX
from raiden_common.tests.utils.factories import make_token_network_address
from raiden_common.utils.typing import Address, ChannelID, TokenNetworkAddress, TransactionHash

from monitoring_service.database import Database
from monitoring_service.events import ActionMonitoringTriggeredEvent, ScheduledEvent
from monitoring_service.service import MonitoringService
from monitoring_service.states import Channel, OnChainUpdateStatus
from raiden_libs.database import hex256
from raiden_libs.utils import to_checksum_address
from tests.constants import DEFAULT_TOKEN_NETWORK_SETTLE_TIMEOUT
from tests.monitoring.monitoring_service.factories import (
    DEFAULT_TOKEN_NETWORK_ADDRESS,
    create_channel,
    create_signed_monitor_request,
)


def test_scheduled_events(ms_database: Database):
    # Add token network used as foreign key
    token_network_address = TokenNetworkAddress(bytes([1] * 20))
    ms_database.conn.execute(
        "INSERT INTO token_network (address, settle_timeout) VALUES (?, ?)",
        [to_checksum_address(token_network_address), DEFAULT_TOKEN_NETWORK_SETTLE_TIMEOUT],
    )

    event1 = ScheduledEvent(
        trigger_timestamp=23 * 15,
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
        trigger_timestamp=24 * 15,
        event=ActionMonitoringTriggeredEvent(
            token_network_address=token_network_address,
            channel_identifier=ChannelID(1),
            non_closing_participant=Address(bytes([1] * 20)),
        ),
    )

    ms_database.upsert_scheduled_event(event2)
    assert ms_database.scheduled_event_count() == 2

    assert len(ms_database.get_scheduled_events(22 * 15)) == 0
    assert len(ms_database.get_scheduled_events(23 * 15)) == 1
    assert len(ms_database.get_scheduled_events(24 * 15)) == 2

    ms_database.upsert_scheduled_event(event1)
    assert ms_database.scheduled_event_count() == 2

    assert len(ms_database.get_scheduled_events(22 * 15)) == 0
    assert len(ms_database.get_scheduled_events(23 * 15)) == 1
    assert len(ms_database.get_scheduled_events(24 * 15)) == 2

    ms_database.remove_scheduled_event(event2)
    assert len(ms_database.get_scheduled_events(22 * 15)) == 0
    assert len(ms_database.get_scheduled_events(23 * 15)) == 1
    assert len(ms_database.get_scheduled_events(24 * 15)) == 1


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

    assert restored == request


def test_save_and_load_channel(ms_database: Database):
    ms_database.conn.execute(
        "INSERT INTO token_network (address, settle_timeout) VALUES (?, ?)",
        [to_checksum_address(DEFAULT_TOKEN_NETWORK_ADDRESS), DEFAULT_TOKEN_NETWORK_SETTLE_TIMEOUT],
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


def test_saveing_multiple_channel(ms_database: Database):
    ms_database.conn.execute(
        "INSERT INTO token_network (address, settle_timeout) VALUES (?, ?)",
        [to_checksum_address(DEFAULT_TOKEN_NETWORK_ADDRESS), DEFAULT_TOKEN_NETWORK_SETTLE_TIMEOUT],
    )
    tn_address2 = make_token_network_address()
    ms_database.conn.execute(
        "INSERT INTO token_network (address, settle_timeout) VALUES (?, ?)",
        [to_checksum_address(tn_address2), DEFAULT_TOKEN_NETWORK_SETTLE_TIMEOUT],
    )

    channel1 = create_channel()
    channel2 = create_channel()
    channel2.token_network_address = tn_address2

    ms_database.upsert_channel(channel1)
    loaded_channel1 = ms_database.get_channel(
        token_network_address=channel1.token_network_address, channel_id=channel1.identifier
    )
    assert loaded_channel1 == channel1
    assert ms_database.channel_count() == 1

    ms_database.upsert_channel(channel2)
    loaded_channel2 = ms_database.get_channel(
        token_network_address=channel2.token_network_address, channel_id=channel2.identifier
    )
    assert loaded_channel2 == channel2
    assert ms_database.channel_count() == 2


def test_purge_old_monitor_requests(
    ms_database: Database,
    build_request_monitoring,
    request_collector,
    monitoring_service: MonitoringService,
):
    # We'll test the purge on MRs for three different channels
    req_mons = [
        build_request_monitoring(channel_id=1),
        build_request_monitoring(channel_id=2),
        build_request_monitoring(channel_id=3),
    ]
    for req_mon in req_mons:
        request_collector.on_monitor_request(req_mon)

    # Channel 1 exists in the db
    token_network_address = req_mons[0].balance_proof.token_network_address
    ms_database.conn.execute(
        "INSERT INTO token_network VALUES (?, ?)",
        [to_checksum_address(token_network_address), DEFAULT_TOKEN_NETWORK_SETTLE_TIMEOUT],
    )
    ms_database.upsert_channel(
        Channel(
            identifier=ChannelID(1),
            token_network_address=token_network_address,
            participant1=Address(b"1" * 20),
            participant2=Address(b"2" * 20),
        )
    )

    # The request for channel 2 is recent (default), but the one for channel 3
    # has been added 16 minutes ago.
    saved_at = (datetime.utcnow() - timedelta(minutes=16)).timestamp()
    ms_database.conn.execute(
        """
        UPDATE monitor_request
        SET saved_at = ?
        WHERE channel_identifier = ?
        """,
        [saved_at, hex256(3)],
    )

    monitoring_service._purge_old_monitor_requests()  # pylint: disable=protected-access
    remaining_mrs = ms_database.conn.execute(
        """
        SELECT channel_identifier, waiting_for_channel
        FROM monitor_request ORDER BY channel_identifier
        """
    ).fetchall()
    assert [tuple(mr) for mr in remaining_mrs] == [(1, False), (2, True)]

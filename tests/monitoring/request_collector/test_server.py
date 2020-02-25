# pylint: disable=redefined-outer-name
from unittest.mock import Mock, patch

import pytest
from eth_utils import to_checksum_address

from monitoring_service.constants import CHANNEL_CLOSE_MARGIN
from monitoring_service.database import Database
from monitoring_service.states import Channel
from raiden.storage.serialization.serializer import DictSerializer
from raiden.utils.typing import Address


def test_invalid_request(ms_database, build_request_monitoring, request_collector):
    def store_successful(reward_proof_signature=None, non_closing_participant=None, **kwargs):
        request_monitoring = build_request_monitoring(**kwargs)
        rm_dict = DictSerializer.serialize(request_monitoring)
        if reward_proof_signature:
            rm_dict["signature"] = reward_proof_signature
        if non_closing_participant:
            rm_dict["non_closing_participant"] = non_closing_participant
        request_collector.on_monitor_request(DictSerializer.deserialize(rm_dict))
        return ms_database.monitor_request_count() == 1

    # bad signature
    invalid_sig = "0x" + "1" * 130
    assert not store_successful(reward_proof_signature=invalid_sig)

    # wrong chain_id
    assert not store_successful(chain_id=2)

    # wrong non_closing_participant
    assert not store_successful(non_closing_participant=b"1" * 20)

    # success
    assert store_successful()


def test_ignore_old_nonce(ms_database: Database, build_request_monitoring, request_collector):
    def stored_mr_after_proccessing(amount, nonce):
        request_monitoring = build_request_monitoring(amount=amount, nonce=nonce)
        request_collector.on_monitor_request(request_monitoring)
        return ms_database.get_monitor_request(
            token_network_address=request_monitoring.balance_proof.token_network_address,
            channel_id=request_monitoring.balance_proof.channel_identifier,
            non_closing_signer=request_monitoring.non_closing_signer,
        )

    # first_write
    mr = stored_mr_after_proccessing(amount=1, nonce=1)
    assert mr
    initial_hash = mr.balance_hash

    # update without increasing nonce must fail
    assert stored_mr_after_proccessing(amount=2, nonce=1).balance_hash == initial_hash

    # update without higher nonce must succeed
    assert stored_mr_after_proccessing(amount=2, nonce=2).balance_hash != initial_hash


def test_request_collector_doesnt_crash_with_invalid_messages(request_collector):
    # We want to test that the request collector does not crash,
    # in case an assertion on the MonitorRequest fails
    # In theory, the collector crashed before, when on_monitor_request raised an AssertionError
    with patch.object(request_collector, "on_monitor_request", side_effect=AssertionError):
        request_collector.handle_message(Mock())


@pytest.mark.parametrize(
    "closing_block", [None, 100 - CHANNEL_CLOSE_MARGIN, 100 - CHANNEL_CLOSE_MARGIN + 1]
)
def test_ignore_mr_for_closed_channel(
    request_collector, build_request_monitoring, ms_database, closing_block
):
    """ MRs that come in >=10 blocks after the channel has been closed must be ignored."""
    request_monitoring = build_request_monitoring()
    ms_database.conn.execute("UPDATE blockchain SET latest_committed_block = ?", [100])
    ms_database.conn.execute(
        "INSERT INTO token_network(address) VALUES (?)",
        [to_checksum_address(request_monitoring.balance_proof.token_network_address)],
    )
    ms_database.upsert_channel(
        Channel(
            identifier=request_monitoring.balance_proof.channel_identifier,
            token_network_address=request_monitoring.balance_proof.token_network_address,
            participant1=Address(b"1" * 20),
            participant2=Address(b"2" * 20),
            settle_timeout=10,
            closing_block=closing_block if closing_block else None,
        )
    )
    request_collector.on_monitor_request(request_monitoring)

    # When the channel is not closed, of the closing is less than 10 blocks
    # before the current block (100), the MR must be saved.
    expected_mrs = 0 if closing_block == 100 - CHANNEL_CLOSE_MARGIN else 1
    assert ms_database.monitor_request_count() == expected_mrs

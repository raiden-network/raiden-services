# pylint: disable=redefined-outer-name
from unittest.mock import Mock, patch

from eth_utils import to_checksum_address

from raiden.storage.serialization.serializer import DictSerializer


def test_invalid_request(ms_database, build_request_monitoring, request_collector):
    def store_successful(reward_proof_signature=None, **kwargs):
        request_monitoring = build_request_monitoring(**kwargs)
        rm_dict = DictSerializer.serialize(request_monitoring)
        if reward_proof_signature:
            rm_dict["signature"] = reward_proof_signature
        request_collector.on_monitor_request(DictSerializer.deserialize(rm_dict))
        return ms_database.monitor_request_count() == 1

    # bad signature
    invalid_sig = "0x" + "1" * 130
    assert not store_successful(reward_proof_signature=invalid_sig)

    # wrong chain_id
    assert not store_successful(chain_id=2)

    # success
    assert store_successful()


def test_ignore_old_nonce(ms_database, build_request_monitoring, request_collector):
    def stored_mr_after_proccessing(amount, nonce):
        request_monitoring = build_request_monitoring(amount=amount, nonce=nonce)
        request_collector.on_monitor_request(request_monitoring)
        return ms_database.get_monitor_request(
            token_network_address=to_checksum_address(
                request_monitoring.balance_proof.token_network_address
            ),
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

# pylint: disable=redefined-outer-name
import pytest
from eth_utils import encode_hex, to_checksum_address

from monitoring_service.states import HashedBalanceProof
from raiden.messages import RequestMonitoring
from raiden.utils.typing import ChannelID, TokenAmount, TokenNetworkAddress
from raiden_contracts.tests.utils import get_random_privkey
from raiden_libs.utils import private_key_to_address


@pytest.fixture
def build_request_monitoring():
    non_closing_privkey = get_random_privkey()
    non_closing_address = private_key_to_address(non_closing_privkey)

    def f(chain_id=1, amount=50, nonce=1):
        balance_proof = HashedBalanceProof(
            channel_identifier=ChannelID(1),
            token_network_address=TokenNetworkAddress(b"1" * 20),
            chain_id=chain_id,
            nonce=nonce,
            additional_hash="",
            balance_hash=encode_hex(bytes([amount])),
            priv_key=get_random_privkey(),
        )
        request_monitoring = balance_proof.get_request_monitoring(
            privkey=non_closing_privkey, reward_amount=TokenAmount(55)
        )

        # usually not a property of RequestMonitoring, but added for convenience in these tests
        request_monitoring.non_closing_signer = to_checksum_address(  # type: ignore
            non_closing_address
        )
        return request_monitoring

    return f


def test_invalid_request(ms_database, build_request_monitoring, request_collector):
    def store_successful(reward_proof_signature=None, **kwargs):
        request_monitoring = build_request_monitoring(**kwargs)
        rm_dict = request_monitoring.to_dict()
        if reward_proof_signature:
            rm_dict["reward_proof_signature"] = reward_proof_signature
        request_collector.on_monitor_request(RequestMonitoring.from_dict(rm_dict))
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

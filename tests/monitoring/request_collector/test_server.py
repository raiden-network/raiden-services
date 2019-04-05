import pytest
from eth_utils import decode_hex, to_checksum_address

from raiden.messages import RequestMonitoring, SignedBlindedBalanceProof
from raiden.tests.utils.messages import make_balance_proof
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import TokenAmount
from raiden_contracts.tests.utils import get_random_privkey


@pytest.fixture
def build_request_monitoring():
    signer = LocalSigner(decode_hex(get_random_privkey()))
    non_closing_signer = LocalSigner(decode_hex(get_random_privkey()))

    def f(chain_id=1, **kwargs):
        balance_proof = make_balance_proof(signer=signer, **kwargs)
        balance_proof.chain_id = chain_id
        partner_signed_balance_proof = SignedBlindedBalanceProof.from_balance_proof_signed_state(
            balance_proof
        )
        request_monitoring = RequestMonitoring(
            onchain_balance_proof=partner_signed_balance_proof, reward_amount=TokenAmount(55)
        )
        request_monitoring.sign(non_closing_signer)

        # usually not a property of RequestMonitoring, but added for convenience in these tests
        request_monitoring.non_closing_signer = to_checksum_address(  # type: ignore
            non_closing_signer.address
        )
        return request_monitoring

    return f


def test_invalid_request(ms_database, build_request_monitoring, request_collector):
    def store_successful(reward_proof_signature=None, **kwargs):
        request_monitoring = build_request_monitoring(**kwargs)
        rm_dict = request_monitoring.to_dict()
        if reward_proof_signature:
            rm_dict['reward_proof_signature'] = reward_proof_signature
        request_collector.on_monitor_request(RequestMonitoring.from_dict(rm_dict))
        return ms_database.monitor_request_count() == 1

    # bad signature
    invalid_sig = '0x' + '1' * 130
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

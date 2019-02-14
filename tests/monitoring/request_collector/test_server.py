from eth_utils import decode_hex

from raiden.messages import RequestMonitoring, SignedBlindedBalanceProof
from raiden.tests.utils.messages import make_balance_proof
from raiden.utils.signer import LocalSigner


def test_request_validation(
        ms_database,
        get_random_privkey,
        request_collector,
):
    # build a valid RequestMonitoring instance
    signer = LocalSigner(decode_hex(get_random_privkey()))
    partner_signer = LocalSigner(decode_hex(get_random_privkey()))
    balance_proof = make_balance_proof(signer=partner_signer, amount=1)
    partner_signed_balance_proof = SignedBlindedBalanceProof.from_balance_proof_signed_state(
        balance_proof,
    )
    request_monitoring = RequestMonitoring(
        onchain_balance_proof=partner_signed_balance_proof,
        reward_amount=55,
    )
    request_monitoring.sign(signer)

    def store_successful(**kwargs):
        rm_dict = request_monitoring.to_dict()
        for key, val in kwargs.items():
            rm_dict[key] = val
        request_collector.on_monitor_request(
            RequestMonitoring.from_dict(rm_dict),
        )
        return ms_database.monitor_request_count() == 1

    # bad signatures
    invalid_sig = '0x' + '0' * 130
    assert not store_successful(reward_proof_signature=invalid_sig)
    assert not store_successful(reward_proof_signature=invalid_sig)
    assert not store_successful(reward_proof_signature=invalid_sig)

    # success
    assert store_successful()

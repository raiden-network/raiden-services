from math import isclose

from eth_utils import decode_hex, is_same_address

from raiden_libs.utils.signing import eth_verify


def test_client_multiple_topups(generate_raiden_clients):
    deposits = [1, 1, 2, 3, 5, 8, 13]
    c1, c2 = generate_raiden_clients(2)
    channel_id = c1.open_channel(c2.address)
    assert channel_id > 0
    [c1.deposit_to_channel(c2.address, x) for x in deposits]
    channel_info = c1.get_our_channel_state(c2.address)
    assert sum(deposits) == channel_info['deposit']


def test_client_fee_info(generate_raiden_clients):
    c1, c2 = generate_raiden_clients(2)
    channel_id = c1.open_channel(c2.address)
    assert channel_id > 0

    fi = c1.get_fee_info(c2.address, nonce=5, percentage_fee=0.1, chain_id=2)
    fee_info_signer = eth_verify(decode_hex(fi.signature), fi.serialize_bin())

    assert is_same_address(fee_info_signer, c1.address)

    assert fi.nonce == 5
    assert isclose(fi.percentage_fee, 0.1)
    assert fi.chain_id == 2


def test_message_signature(generate_raiden_clients):
    c1, c2 = generate_raiden_clients(2)
    c1.open_channel(c2.address)

    balance_proof = c1.get_balance_proof(c2.address, nonce=1, transferred_amount=5)
    assert is_same_address(balance_proof.signer, c1.address)
    monitor_request = c1.get_monitor_request(c2.address, balance_proof, 1, c2.address)
    assert is_same_address(monitor_request.reward_proof_signer, c1.address)
    fee_info = c1.get_fee_info(c2.address)
    assert is_same_address(fee_info.signer, c1.address)

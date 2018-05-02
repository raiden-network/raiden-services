import pytest

from eth_utils import decode_hex, is_same_address

from raiden_libs.utils.signing import eth_verify


def test_client_multiple_topups(generate_raiden_clients):
    deposits = [1, 1, 2, 3, 5, 8, 13]
    c1, c2 = generate_raiden_clients(2)
    channel_id = c1.open_channel(c2.address)
    assert channel_id > 0
    [c1.deposit_to_channel(c2.address, x) for x in deposits]
    channel_info = c1.get_own_channel_info(c2.address)
    assert sum(deposits) == channel_info['deposit']


def test_client_fee_info(generate_raiden_clients):
    c1, c2 = generate_raiden_clients(2)
    channel_id = c1.open_channel(c2.address)
    assert channel_id > 0

    fi = c1.get_fee_info(c2.address, nonce=5, relative_fee=1000, chain_id=2)
    fee_info_signer = eth_verify(decode_hex(fi.signature), fi.serialize_bin())

    assert is_same_address(fee_info_signer, c1.address)

    assert fi.nonce == 5
    assert fi.relative_fee == 1000
    assert fi.chain_id == 2


@pytest.mark.skip(reason='MSC not yet merged to master')
def test_message_signature(generate_raiden_clients):
    c1, c2 = generate_raiden_clients(2)
    c1.open_channel(c2.address)

    balance_proof = c1.get_balance_proof(
        c2.address,
        nonce=1,
        transferred_amount=5,
        locksroot='0x%064x' % 0,
        locked_amount=0
    )
    assert is_same_address(balance_proof.signer, c1.address)
    monitor_request = c1.get_monitor_request(c2.address, balance_proof, 1, c2.address)
    assert is_same_address(monitor_request.reward_proof_signer, c1.address)
    fee_info = c1.get_fee_info(c2.address)
    assert is_same_address(fee_info.signer, c1.address)


def test_close_settle(generate_raiden_clients, wait_for_blocks, standard_token_contract):
    """Tests channel life cycle for mocked client"""
    c1, c2 = generate_raiden_clients(2)
    c1.open_channel(c2.address)

    initial_balance_c1 = standard_token_contract.functions.balanceOf(c1.address).call()
    initial_balance_c2 = standard_token_contract.functions.balanceOf(c2.address).call()
    transfer_c1 = 5
    transfer_c2 = 6

    c1.deposit_to_channel(c2.address, 100)
    c2.deposit_to_channel(c1.address, 100)

    balance_proof = c2.get_balance_proof(
        c1.address,
        nonce=1,
        transferred_amount=transfer_c1,
        locked_amount=0,
        locksroot='0x%064x' % 0,
        additional_hash='0x%064x' % 0
    )
    balance_proof_c2 = c1.get_balance_proof(
        c2.address,
        nonce=2,
        transferred_amount=transfer_c2,
        locked_amount=0,
        locksroot='0x%064x' % 0,
        additional_hash='0x%064x' % 0
    )

    c1.close_channel(c2.address, balance_proof)

    c2.update_transfer(c1.address, balance_proof_c2)

    wait_for_blocks(40)
    c1.settle_channel(
        c2.address,
        (balance_proof_c2.transferred_amount, balance_proof.transferred_amount),
        (balance_proof_c2.locked_amount, balance_proof.locked_amount),
        (balance_proof_c2.locksroot, balance_proof.locksroot)
    )

    final_balance_c1 = standard_token_contract.functions.balanceOf(c1.address).call()
    final_balance_c2 = standard_token_contract.functions.balanceOf(c2.address).call()
    assert final_balance_c1 == initial_balance_c1 + (transfer_c1 - transfer_c2)
    assert final_balance_c2 == initial_balance_c2 - (transfer_c1 - transfer_c2)

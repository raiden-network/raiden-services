import random

import pytest
from eth_utils import is_same_address

from raiden_libs.messages import BalanceProof, Message
from raiden_libs.types import Address, ChannelIdentifier
from raiden_libs.utils import UINT256_MAX, encode_hex, eth_sign


def get_random_channel_id() -> ChannelIdentifier:
    return ChannelIdentifier(random.randrange(0, UINT256_MAX))


def test_serialize_deserialize(get_random_bp, get_random_privkey):
    bp = get_random_bp()
    privkey = get_random_privkey()
    bp.signature = encode_hex(
        eth_sign(
            privkey,
            bp.serialize_bin(),
        ),
    )
    serialized_message = bp.serialize_full()

    deserialized_message = Message.deserialize(serialized_message)
    assert isinstance(deserialized_message, BalanceProof)


def test_balance_proof_address_setter(get_random_bp):
    # test set of checksummed addrs
    bp = get_random_bp()

    # set of an invalid address should raise ValueError
    with pytest.raises(ValueError):
        bp.token_network_address = 123456789
    with pytest.raises(ValueError):
        bp.token_network_address = '0x11e14d102DA61F1a5cA36cfa96C3B831332357b4'


def test_balance_proof():
    # test balance proof with computed balance hash
    balance_proof = BalanceProof(
        channel_identifier=get_random_channel_id(),
        token_network_address=Address('0x82dd0e0eA3E84D00Cc119c46Ee22060939E5D1FC'),
        nonce=1,
        chain_id=321,
        transferred_amount=5,
        locksroot='0x%064x' % 5,
        additional_hash='0x%064x' % 0,
    )
    serialized = balance_proof.serialize_data()

    assert serialized['channel_identifier'] == balance_proof.channel_identifier
    assert is_same_address(
        serialized['token_network_address'],
        balance_proof.token_network_address,
    )
    assert serialized['nonce'] == balance_proof.nonce
    assert serialized['chain_id'] == balance_proof.chain_id
    assert serialized['additional_hash'] == balance_proof.additional_hash
    assert serialized['balance_hash'] == balance_proof.balance_hash

    assert serialized['locksroot'] == balance_proof.locksroot
    assert serialized['transferred_amount'] == balance_proof.transferred_amount
    assert serialized['locked_amount'] == balance_proof.locked_amount

    # test balance proof with balance hash set from constructor
    balance_proof = BalanceProof(
        channel_identifier=get_random_channel_id(),
        token_network_address=Address('0x82dd0e0eA3E84D00Cc119c46Ee22060939E5D1FC'),
        nonce=1,
        chain_id=321,
        balance_hash='0x%064x' % 5,
        locked_amount=0,
        additional_hash='0x%064x' % 0,
    )
    serialized = balance_proof.serialize_data()

    with pytest.raises(KeyError):
        serialized['transferred_amount']

    assert serialized['channel_identifier'] == balance_proof.channel_identifier
    assert is_same_address(
        serialized['token_network_address'],
        balance_proof.token_network_address,
    )
    assert serialized['nonce'] == balance_proof.nonce
    assert serialized['chain_id'] == balance_proof.chain_id
    assert serialized['additional_hash'] == balance_proof.additional_hash
    assert serialized['balance_hash'] == balance_proof.balance_hash

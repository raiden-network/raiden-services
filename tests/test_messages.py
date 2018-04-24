from typing import Dict

import pytest

from raiden_libs.messages import BalanceProof, Message, FeeInfo
from raiden_libs.exceptions import MessageTypeError


def test_serialize_deserialize(get_random_bp):
    bp = get_random_bp()
    serialized_message = bp.serialize_full()

    deserialized_message = Message.deserialize(serialized_message)
    assert isinstance(deserialized_message, BalanceProof)


def test_balance_proof(get_random_bp):
    # test set of checksummed addrs
    bp = get_random_bp()

    # set of an invalid address should raise ValueError
    with pytest.raises(ValueError):
        bp.contract_address = 123456789
    with pytest.raises(ValueError):
        bp.contract_address = '0x11e14d102DA61F1a5cA36cfa96C3B831332357b4'


def test_fee_info():
    message: Dict = dict(
        message_type='FeeInfo',
        token_network_address='0x82dd0e0eA3E84D00Cc119c46Ee22060939E5D1FC',
        chain_id=1,
        channel_identifier=123,
        nonce=1,
        percentage_fee='0.1',
        signature='signature'
    )

    deserialized_message = Message.deserialize(message)
    assert isinstance(deserialized_message, FeeInfo)


def test_deserialize_with_required_type():
    message: Dict = dict(
        message_type='FeeInfo',
        token_network_address='0x82dd0e0eA3E84D00Cc119c46Ee22060939E5D1FC',
        chain_id=1,
        channel_identifier=123,
        nonce=1,
        percentage_fee='0.1',
        signature='signature'
    )

    deserialized_message = Message.deserialize(message, FeeInfo)
    assert isinstance(deserialized_message, FeeInfo)

    # during deseriaisation the `message_type`is removed, add it back
    message['message_type'] = 'FeeInfo'
    with pytest.raises(MessageTypeError):
        Message.deserialize(message, BalanceProof)

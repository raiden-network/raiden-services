import pytest
import json

from monitoring_service.messages import BalanceProof, Message
from monitoring_service.utils import privkey_to_addr
from monitoring_service.exceptions import MessageSignatureError

channel_address = '0x11e14d102DA61F1a5cA36cfa96C3B831332357b3'
participant1 = '0x2E8ffB67C9929Bf817d375541f0A8f4E437Ee7BF'
participant2 = '0xd046C85261E50d18c42F4972D9B32e7F874FA6a1'


def test_serialize_deserialize():
    bp = BalanceProof(channel_address, participant1, participant2)
    privkey = '0x1'
    serialized_message = bp.serialize_full(privkey)

    deserialized_message = Message.deserialize(serialized_message)
    assert isinstance(deserialized_message, BalanceProof)


def test_balance_proof():
    # test set of checksummed addrs
    bp = BalanceProof(channel_address, participant1, participant2)

    # set of an invalid address should raise ValueError
    with pytest.raises(ValueError):
        bp.channel_address = 123456789
    with pytest.raises(ValueError):
        bp.channel_address = '0x11e14d102DA61F1a5cA36cfa96C3B831332357b4'
    with pytest.raises(ValueError):
        bp.participant1 = '0x2E8ffB67C9929Bf817d375541f0A8f4E437Ee7B0'
    with pytest.raises(ValueError):
        bp.participant2 = '0xd046C85261E50d18c42F4972D9B32e7F874FA6a2'


def test_sign(get_random_bp, get_random_privkey):
    # test valid, signed message
    msg = get_random_bp()
    pk = get_random_privkey()
    pk1 = get_random_privkey()
    addr = privkey_to_addr(pk)
    data = msg.serialize_full(pk)
    signed_msg = Message.deserialize(data)
    assert signed_msg.signer == addr
    assert signed_msg.header['sender'] == addr

    # test case where signer doesn't match value in the header
    data1 = msg.serialize_full(pk1)
    json_data = json.loads(data)
    json_data1 = json.loads(data1)
    json_data['signature'] = json_data1['signature']
    with pytest.raises(MessageSignatureError):
        signed_msg = Message.deserialize(json_data)

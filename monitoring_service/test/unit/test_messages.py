import pytest
import json

from monitoring_service.messages import BalanceProof, Message
from monitoring_service.utils import privkey_to_addr, pubkey_to_addr
from monitoring_service.exceptions import MessageSignatureError, MessageFormatError
from coincurve import PrivateKey, PublicKey
from eth_utils import remove_0x_prefix, is_same_address

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
    # invalid addr checksum
    with pytest.raises(ValueError):
        bp.participant1 = '0x2E8ffB67C9929Bf817d375541f0A8f4E437Ee7B0'
    with pytest.raises(ValueError):
        bp.participant2 = '0xd046C85261E50d18c42F4972D9B32e7F874FA6a2'


def test_sign(get_random_bp, get_random_privkey, get_random_address):
    # test valid, signed message
    msg = get_random_bp()
    pk = get_random_privkey()
    pk1 = get_random_privkey()
    addr = privkey_to_addr(pk)
    data = msg.serialize_full(pk)
    signed_msg = Message.deserialize(data)
    assert signed_msg.signer == addr
    assert signed_msg.header['sender'] == addr

    # test case where signature doesn't match value in the header
    data1 = msg.serialize_full(pk1)
    json_data = json.loads(data)
    json_data1 = json.loads(data1)
    json_data['signature'] = json_data1['signature']
    with pytest.raises(MessageSignatureError):
        signed_msg = Message.deserialize(json_data)

    # test invalid 'sender' field in the message header
    # (similar to previous test but vice versa)
    json_data = msg.serialize_full(pk)
    json_data = json.loads(json_data)
    data = json.loads(json_data['data'])
    data['header']['sender'] = get_random_address()
    json_data['data'] = json.dumps(data)
    with pytest.raises(MessageSignatureError):
        Message.deserialize(json_data)

    # test invalid signature format
    json_data['signature'] = '0xabcdef'
    with pytest.raises(MessageFormatError):
        signed_msg = Message.deserialize(json_data)


def test_sign_and_recover(get_random_privkey, get_random_bp):
    msg = get_random_bp()
    privkey = get_random_privkey()
    msg.participant1 = privkey_to_addr(privkey)
    pk = PrivateKey.from_hex(remove_0x_prefix(privkey))
    signature = pk.sign_recoverable(msg.serialize_bin())

    pubk = PublicKey.from_signature_and_message(signature, msg.serialize_bin())
    pubk_addr = pubkey_to_addr(pubk)
    assert is_same_address(pubk_addr, msg.participant1)

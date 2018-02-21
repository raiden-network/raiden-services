from monitoring_service.messages import BalanceProof, Message
import pytest

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

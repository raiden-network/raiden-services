import pytest

from raiden_libs.messages import BalanceProof, Message


def test_serialize_deserialize(get_random_bp):
    bp = get_random_bp()
    privkey = '0x1'
    serialized_message = bp.serialize_full(privkey)

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

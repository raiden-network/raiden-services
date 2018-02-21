import pytest
import random
from monitoring_service.utils import privkey_to_addr
from monitoring_service.messages import BalanceProof


@pytest.fixture
def get_random_privkey():
    return lambda: "0x%032x" % random.randint(1, 0xffffffffffffffffffffffffffffffff)


@pytest.fixture
def get_random_address(get_random_privkey):
    def f():
        return privkey_to_addr(get_random_privkey())
    return f


@pytest.fixture
def get_random_bp(get_random_address):
    """Returns a balance proof filled in with a random values"""
    def f():
        p1, p2 = get_random_address(), get_random_address()
        channel_address = get_random_address()
        return BalanceProof(channel_address, p1, p2)
    return f

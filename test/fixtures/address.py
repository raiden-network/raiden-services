import pytest
import random
from monitoring_service.utils import privkey_to_addr


@pytest.fixture
def get_random_address():
    def f():
        return privkey_to_addr(hex(random.randint(0, 0xffff)))
    return f

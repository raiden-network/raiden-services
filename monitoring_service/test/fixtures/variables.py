import pytest
import os
from monitoring_service import __file__ as MS_PATH


@pytest.fixture
def rest_host():
    return 'localhost'


@pytest.fixture
def rest_port():
    return 5001


@pytest.fixture(scope='session')
def use_tester():
    return True


@pytest.fixture(scope='session')
def smart_contracts_path():
    base_path = os.path.dirname(MS_PATH)
    base_path = os.path.dirname(base_path)
    return os.path.join(base_path, 'compiled')


@pytest.fixture(scope='session')
def kovan_block_time():
    return 4

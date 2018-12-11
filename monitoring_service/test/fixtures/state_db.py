import pytest

from monitoring_service.state_db import StateDBSqlite
from monitoring_service.test.mockups import StateDBMock


@pytest.fixture
def state_db_mock(get_random_address):
    return StateDBMock()


@pytest.fixture
def state_db_sqlite(get_random_address):
    return StateDBSqlite(':memory:')

import pytest

from monitoring_service.state_db import StateDBSqlite
from monitoring_service.test.mockups import StateDBMock


@pytest.fixture
def state_db_mock(get_random_address):
    return StateDBMock()


@pytest.fixture
def state_db_sqlite(get_random_address):
    state_db_sqlite = StateDBSqlite(':memory:')
    state_db_sqlite.setup_db(1, get_random_address(), get_random_address())
    return state_db_sqlite

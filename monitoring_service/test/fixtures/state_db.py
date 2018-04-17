import pytest
from monitoring_service.state_db import StateDBSqlite
from monitoring_service.test.mockups import StateDBMock


@pytest.fixture
def state_db_mock(get_random_address):
    db = StateDBMock()
    db.setup_db(0, get_random_address(), get_random_address())
    return db


@pytest.fixture
def state_db_sqlite(get_random_address):
    db = StateDBSqlite(':memory:')
    db.setup_db(0, get_random_address(), get_random_address())
    return db

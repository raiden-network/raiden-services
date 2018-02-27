import pytest
from monitoring_service.state_db import StateDB


@pytest.fixture
def state_db(get_random_address):
    db = StateDB(':memory:')
    db.setup_db(0, get_random_address(), get_random_address())
    return db

import pytest
from request_collector.state_db import StateDBSqlite


@pytest.fixture
def state_db_sqlite(
    ms_database,
):
    return StateDBSqlite(conn=ms_database.conn)

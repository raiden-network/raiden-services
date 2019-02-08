import sqlite3
from typing import Iterable
import json

from monitoring_service.database import BaseDatabase


def convert_hex(raw: bytes) -> int:
    return int(raw, 16)


sqlite3.register_converter('HEX_INT', convert_hex)
sqlite3.register_converter('JSON', json.loads)


def adapt_tuple(t: tuple) -> str:
    return json.dumps(t)


sqlite3.register_adapter(tuple, adapt_tuple)


class StateDBSqlite(BaseDatabase):
    def __init__(self, filename: str = None, conn=None):
        if filename:
            assert conn is None
            super(StateDBSqlite, self).__init__(filename)
        else:
            # for test fixture only
            assert conn
            self.conn = conn

    def fetch_scalar(self, query: str, query_args: Iterable = ()):
        """ Helper function to fetch a single field of a single row """
        return self.conn.execute(query, query_args).fetchone()[0]

    def chain_id(self):
        return int(self.fetch_scalar("SELECT chain_id FROM blockchain"))

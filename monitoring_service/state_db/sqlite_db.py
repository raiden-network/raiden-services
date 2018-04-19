import sqlite3
from eth_utils import is_checksum_address
import os

from .queries import DB_CREATION_SQL, ADD_MONITOR_REQUEST_SQL, UPDATE_METADATA_SQL
from .db import StateDB


def dict_factory(cursor, row):
    """make sqlite result a dict with keys being column names"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class StateDBSqlite(StateDB):
    def __init__(self, filename):
        self.filename = filename
        self.conn = sqlite3.connect(self.filename, isolation_level="EXCLUSIVE")
        self.conn.row_factory = dict_factory
        if filename not in (None, ':memory:'):
            os.chmod(filename, 0o600)

    def setup_db(self, network_id: int, contract_address: str, receiver: str):
        """Initialize an empty database. Call this if `is_initialized()` returns False"""
        assert is_checksum_address(receiver)
        assert is_checksum_address(contract_address)
        assert network_id >= 0
        self.conn.executescript(DB_CREATION_SQL)
        self.conn.execute(UPDATE_METADATA_SQL, [network_id, contract_address, receiver])
        self.conn.commit()

    @property
    def monitor_requests(self) -> dict:
        c = self.conn.cursor()
        c.execute('SELECT * FROM `monitor_requests`')
        ret = []
        for x in c.fetchall():
            x['channel_identifier'] = int(x['channel_identifier'], 16)
            x['transferred_amount'] = int(x['transferred_amount'], 16)
            x['reward_amount'] = int(x['reward_amount'], 16)
            x['nonce'] = int(x['nonce'], 16)
            ret.append(x)

        return {
            x['channel_identifier']: x
            for x in ret
        }

    def store_monitor_request(self, monitor_request) -> None:
        StateDBSqlite.check_monitor_request(monitor_request)
        params = [
            hex(monitor_request['channel_identifier']),
            hex(monitor_request['nonce']),
            hex(monitor_request['transferred_amount']),
            monitor_request['locksroot'],
            monitor_request['extra_hash'],
            monitor_request['balance_proof_signature'],
            monitor_request['reward_sender_address'],
            monitor_request['reward_proof_signature'],
            hex(monitor_request['reward_amount']),
            monitor_request['token_network_address']
        ]
        self.conn.execute(ADD_MONITOR_REQUEST_SQL, params)

    def get_monitor_request(self, channel_id: int) -> dict:
        assert channel_id > 0
        # TODO unconfirmed topups
        c = self.conn.cursor()
        sql = 'SELECT rowid,* FROM `monitor_requests` WHERE `channel_id` = ?'
        c.execute(sql, [hex(channel_id)])
        result = c.fetchone()
        assert c.fetchone() is None
        return result

    def delete_monitor_request(self, channel_id: int) -> None:
        assert channel_id > 0
        c = self.conn.cursor()
        sql = 'DELETE FROM `monitor_requests` WHERE `channel_id` = ?'
        c.execute(sql, [hex(channel_id)])
        assert c.fetchone() is None

    def is_initialized(self) -> bool:
        c = self.conn.cursor()
        c.execute("SELECT name FROM `sqlite_master` WHERE type='table' AND name='metadata'")
        return c.fetchone() is not None

    @staticmethod
    def check_monitor_request(bp):
        assert bp['channel_identifier'] > 0
        assert is_checksum_address(bp['token_network_address'])
        assert is_checksum_address(bp['reward_sender_address'])
        assert is_checksum_address(bp['monitor_address'])

    def chain_id(self):
        c = self.conn.cursor()
        c.execute("SELECT chain_id FROM `metadata`")
        result = c.fetchone()
        assert c.fetchone() is None
        return int(result)

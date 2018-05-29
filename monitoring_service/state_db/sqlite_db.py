import sqlite3
from eth_utils import is_checksum_address
import os

from .queries import DB_CREATION_SQL, ADD_MONITOR_REQUEST_SQL, UPDATE_METADATA_SQL
from .db import StateDB

from raiden_libs.types import ChannelIdentifier
from raiden_libs.utils import is_channel_identifier


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
            x['reward_amount'] = int(x['reward_amount'], 16)
            x['nonce'] = int(x['nonce'], 16)
            ret.append(x)

        return {
            x['channel_identifier']: x
            for x in ret
        }

    def store_monitor_request(self, monitor_request) -> None:
        StateDBSqlite.check_monitor_request(monitor_request)
        balance_proof = monitor_request['balance_proof']
        params = [
            balance_proof['channel_identifier'],
            balance_proof['balance_hash'],
            hex(balance_proof['nonce']),
            balance_proof['additional_hash'],
            balance_proof['signature'],
            monitor_request['non_closing_signature'],
            monitor_request['reward_proof_signature'],
            hex(monitor_request['reward_amount']),
            balance_proof['token_network_address']
        ]
        self.conn.execute(ADD_MONITOR_REQUEST_SQL, params)

    def get_monitor_request(self, channel_id: ChannelIdentifier) -> dict:
        assert is_channel_identifier(channel_id)
        # TODO unconfirmed topups
        c = self.conn.cursor()
        sql = 'SELECT rowid,* FROM `monitor_requests` WHERE `channel_id` = ?'
        c.execute(sql, [channel_id])
        result = c.fetchone()
        assert c.fetchone() is None
        return result

    def delete_monitor_request(self, channel_id: ChannelIdentifier) -> None:
        assert is_channel_identifier(channel_id)
        c = self.conn.cursor()
        sql = 'DELETE FROM `monitor_requests` WHERE `channel_id` = ?'
        c.execute(sql, [channel_id])
        assert c.fetchone() is None

    def is_initialized(self) -> bool:
        c = self.conn.cursor()
        c.execute("SELECT name FROM `sqlite_master` WHERE type='table' AND name='metadata'")
        return c.fetchone() is not None

    @staticmethod
    def check_monitor_request(monitor_request):
        balance_proof = monitor_request['balance_proof']
        assert is_channel_identifier(balance_proof['channel_identifier'])
        assert is_checksum_address(balance_proof['token_network_address'])
        assert is_checksum_address(monitor_request['monitor_address'])

    def chain_id(self):
        c = self.conn.cursor()
        c.execute("SELECT chain_id FROM `metadata`")
        result = c.fetchone()
        assert c.fetchone() is None
        return int(result)

import sqlite3
from eth_utils import is_checksum_address
import os

from .queries import DB_CREATION_SQL, ADD_BALANCE_PROOF_SQL, UPDATE_METADATA_SQL
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
    def balance_proofs(self) -> dict:
        c = self.conn.cursor()
        c.execute('SELECT * FROM `balance_proofs`')
        ret = []
        for x in c.fetchall():
            x['channel_id'] = int(x['channel_id'], 16)
            x['transferred_amount'] = int(x['transferred_amount'], 16)
            x['nonce'] = int(x['nonce'], 16)
            ret.append(x)

        return {
            x['channel_id']: x
            for x in ret
        }

    def store_balance_proof(self, balance_proof) -> None:
        StateDBSqlite.check_balance_proof(balance_proof)
        params = [
            hex(balance_proof['channel_id']),
            balance_proof['contract_address'],
            balance_proof['participant1'],
            balance_proof['participant2'],
            hex(balance_proof['nonce']),
            hex(balance_proof['transferred_amount']),
            balance_proof['extra_hash'],
            balance_proof['signature'],
            balance_proof['timestamp'],
            balance_proof['chain_id']
        ]
        self.conn.execute(ADD_BALANCE_PROOF_SQL, params)

    def get_balance_proof(self, channel_id: int) -> dict:
        assert channel_id > 0
        # TODO unconfirmed topups
        c = self.conn.cursor()
        sql = 'SELECT rowid,* FROM `balance_proofs` WHERE `channel_id` = ?'
        c.execute(sql, [hex(channel_id)])
        result = c.fetchone()
        assert c.fetchone() is None
        return result

    def delete_balance_proof(self, channel_id: int) -> None:
        assert channel_id > 0
        c = self.conn.cursor()
        sql = 'DELETE FROM `balance_proofs` WHERE `channel_id` = ?'
        c.execute(sql, [hex(channel_id)])
        assert c.fetchone() is None

    def is_initialized(self) -> bool:
        c = self.conn.cursor()
        c.execute("SELECT name FROM `sqlite_master` WHERE type='table' AND name='metadata'")
        return c.fetchone() is not None

    @staticmethod
    def check_balance_proof(bp):
            assert bp['channel_id'] > 0
            assert is_checksum_address(bp['contract_address'])
            assert is_checksum_address(bp['participant1'])
            assert is_checksum_address(bp['participant2'])

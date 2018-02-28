import sqlite3
import os
from eth_utils import is_checksum_address, is_address, to_checksum_address

from .queries import DB_CREATION_SQL, ADD_BALANCE_PROOF_SQL, UPDATE_METADATA_SQL


def dict_factory(cursor, row):
    """make sqlite result a dict with keys being column names"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def check_balance_proof(bp):
        assert is_checksum_address(bp['channel_address'])
        assert is_checksum_address(bp['participant1'])
        assert is_checksum_address(bp['participant2'])
        assert isinstance(bp['balance_proof'], str)


class StateDB:
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
        return {
            x['channel_address']: x
            for x in c.fetchall()
        }

    def store_balance_proof(self, balance_proof) -> None:
        check_balance_proof(balance_proof)
        params = [
            balance_proof['channel_address'],
            balance_proof['participant1'],
            balance_proof['participant2'],
            balance_proof['balance_proof'],
            balance_proof['timestamp']
        ]
        self.conn.execute(ADD_BALANCE_PROOF_SQL, params)

    def get_balance_proof(self, channel_address: str) -> None:
        assert is_address(channel_address)
        # TODO unconfirmed topups
        c = self.conn.cursor()
        sql = 'SELECT rowid,* FROM `balance_proofs` WHERE `channel_address` = ?'
        c.execute(sql, [to_checksum_address(channel_address)])
        result = c.fetchone()
        assert c.fetchone() is None
        return result

    def delete_balance_proof(self, channel_address: str) -> None:
        assert is_address(channel_address)
        c = self.conn.cursor()
        sql = 'DELETE FROM `balance_proofs` WHERE `channel_address` = ?'
        c.execute(sql, [to_checksum_address(channel_address)])
        assert c.fetchone() is None

    def is_initialized(self) -> bool:
        c = self.conn.cursor()
        c.execute("SELECT name FROM `sqlite_master` WHERE type='table' AND name='metadata'")
        return c.fetchone() is not None

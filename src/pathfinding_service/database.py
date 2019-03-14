import os
import sqlite3

import structlog

from raiden_libs.types import Address

log = structlog.get_logger(__name__)
SCHEMA_FILENAME = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'schema.sql',
)


def convert_hex(raw: bytes) -> int:
    return int(raw, 16)


sqlite3.register_converter('HEX_INT', convert_hex)


class PFSDatabase:
    """ Store data that needs to persist between PFS restarts """

    def __init__(self, filename: str, pfs_address: Address):
        log.info('Opening database at ' + filename)
        self.conn = sqlite3.connect(
            filename,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.pfs_address = pfs_address
        self._setup()

    def _setup(self) -> None:
        """ Make sure that the db is initialized """
        initialized = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='iou'",
        ).fetchone()

        if not initialized:
            # create db schema
            with self.conn:
                with open(SCHEMA_FILENAME) as schema_file:
                    self.conn.executescript(schema_file.read())

    def upsert_iou(self, iou: dict):
        self.conn.execute("""
            INSERT OR REPLACE INTO iou (
                sender, amount, expiration_block, signature
            ) VALUES (:sender, :amount, :expiration_block, :signature)
        """, iou)

    def get_iou(self, sender: Address, expiration_block: int):
        row = self.conn.execute(
            """
                SELECT *
                FROM iou
                WHERE sender = ? AND expiration_block = ?
            """,
            [sender, expiration_block],
        ).fetchone()
        if row is None:
            return None

        iou = dict(zip(row.keys(), row))
        iou['receiver'] = self.pfs_address
        return iou

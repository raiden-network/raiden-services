import os
import sqlite3
from typing import Optional

import structlog

from pathfinding_service.model import IOU
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
        if filename != ':memory:':
            os.makedirs(os.path.dirname(filename), exist_ok=True)
        self.conn = sqlite3.connect(
            filename,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,  # Disable sqlite3 module’s implicit transaction management
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

    def upsert_iou(self, iou: IOU):
        iou_dict = IOU.Schema(strict=True).dump(iou)[0]
        self.conn.execute("""
            INSERT OR REPLACE INTO iou (
                sender, amount, expiration_block, signature, claimed
            ) VALUES (:sender, :amount, :expiration_block, :signature, :claimed)
        """, iou_dict)

    def get_iou(
        self,
        sender: Address,
        expiration_block: int = None,
        claimed: bool = None,
    ) -> Optional[IOU]:
        query = "SELECT * FROM iou WHERE sender = ?"
        args: list = [sender]
        if expiration_block is not None:
            query += " AND expiration_block = ?"
            args.append(expiration_block)
        if claimed is not None:
            query += " AND claimed = ?"
            args.append(claimed)

        row = self.conn.execute(query, args).fetchone()
        if row is None:
            return None

        iou_dict = dict(zip(row.keys(), row))
        iou_dict['receiver'] = self.pfs_address
        return IOU.Schema().load(iou_dict)[0]

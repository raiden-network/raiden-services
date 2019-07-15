import os
import sqlite3
import sys
from typing import Any, Dict, Union

import structlog
from eth_utils import to_checksum_address

from raiden.utils.typing import Address, BlockNumber, ChainID, TokenNetworkAddress
from raiden_libs.states import BlockchainState

log = structlog.get_logger(__name__)


def convert_hex(raw: bytes) -> int:
    return int(raw, 16)


def convert_bool(raw: bytes) -> bool:
    if raw == b"1":
        return True
    if raw == b"0":
        return False
    raise Exception("Bad boolean in db:", repr(raw))


sqlite3.register_converter("HEX_INT", convert_hex)
sqlite3.register_converter("BOOLEAN", convert_bool)


def hex256(x: Union[int, str]) -> str:
    """Hex encodes values up to 256 bits into a fixed length

    By including this amount of leading zeros in the hex string, lexicographic
    and numeric ordering are identical. This facilitates working with these
    numbers in the database without native uint256 support.
    """
    if isinstance(x, str):
        x = int(x)
    return "0x{:064x}".format(x)


class BaseDatabase:

    schema_filename: str

    def __init__(self, filename: str, allow_create: bool = False):
        log.info("Opening database", filename=filename)
        if filename == ":memory:":
            self.conn = sqlite3.connect(
                ":memory:",
                detect_types=sqlite3.PARSE_DECLTYPES,
                isolation_level=None,  # Disable sqlite3 module’s implicit transaction management
            )
        else:
            if os.path.dirname(filename):
                os.makedirs(os.path.dirname(filename), exist_ok=True)
            mode = "rwc" if allow_create else "rw"
            self.conn = sqlite3.connect(
                f"file:{filename}?mode={mode}",
                detect_types=sqlite3.PARSE_DECLTYPES,
                uri=True,
                isolation_level=None,  # Disable sqlite3 module’s implicit transaction management
            )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def _setup(
        self,
        chain_id: ChainID,
        receiver: Address,
        sync_start_block: BlockNumber,
        **contract_addresses: Address,
    ) -> None:
        """ Make sure that the db is initialized an matches the given settings """
        assert chain_id >= 0
        hex_addresses: Dict[str, str] = {
            con: to_checksum_address(addr) for con, addr in contract_addresses.items()
        }

        initialized = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='blockchain'"
        ).fetchone()
        settings = dict(chain_id=chain_id, receiver=to_checksum_address(receiver), **hex_addresses)

        if initialized:
            self._check_settings(settings, hex_addresses)
        else:
            # create db schema
            with open(self.schema_filename) as schema_file:
                self.conn.executescript(schema_file.read())
            update_stmt = "UPDATE blockchain SET {}".format(
                ",".join(
                    f"{key} = :{key}"
                    for key in ["chain_id", "receiver", "latest_known_block"] + list(hex_addresses)
                )
            )
            self.conn.execute(update_stmt, dict(latest_known_block=sync_start_block, **settings))

    def _check_settings(
        self, new_settings: Dict[str, Any], contract_addresses: Dict[str, str]
    ) -> None:
        old_settings = self.conn.execute(
            f"""
            SELECT chain_id,
                   {''.join(colname + ',' for colname in contract_addresses)}
                   receiver
            FROM blockchain
        """
        ).fetchone()
        for key, val in new_settings.items():
            old = old_settings[key]
            if old != val:
                log.error(
                    "Mismatch between current settings and settings saved in db: "
                    f"DB was created with {key}='{old}', current_value is '{val}'! "
                    "Either fix your settings or start with a fresh db. "
                    "WARNING: If you delete your db, you will lose earned fees!"
                )
                sys.exit(1)

    def insert(
        self, table_name: str, fields_by_colname: Dict[str, Any], keyword: str = "INSERT"
    ) -> sqlite3.Cursor:
        cols = ", ".join(fields_by_colname.keys())
        values = ", ".join(":" + col_name for col_name in fields_by_colname)
        return self.conn.execute(
            f"{keyword} INTO {table_name}({cols}) VALUES ({values})", fields_by_colname
        )

    def upsert(self, table_name: str, fields_by_colname: Dict[str, Any]) -> sqlite3.Cursor:
        return self.insert(table_name, fields_by_colname, keyword="INSERT OR REPLACE")

    def get_blockchain_state(self) -> BlockchainState:
        blockchain = self.conn.execute("SELECT * FROM blockchain").fetchone()
        token_network_addresses = [
            row[0] for row in self.conn.execute("SELECT address FROM token_network")
        ]
        latest_known_block = blockchain["latest_known_block"]

        return BlockchainState(
            chain_id=blockchain["chain_id"],
            token_network_registry_address=blockchain["token_network_registry_address"],
            monitor_contract_address=blockchain["monitor_contract_address"],
            latest_known_block=latest_known_block,
            token_network_addresses=token_network_addresses,
        )

    def update_blockchain_state(self, state: BlockchainState) -> None:
        self.conn.execute(
            "UPDATE blockchain SET latest_known_block = ?", [state.latest_known_block]
        )
        # assumes that token_networks are not removed
        self.conn.executemany(
            "INSERT OR REPLACE INTO token_network VALUES (?)",
            [[address] for address in state.token_network_addresses],
        )

    def upsert_token_network(self, token_network_address: TokenNetworkAddress) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO token_network VALUES (?)",
            [to_checksum_address(token_network_address)],
        )

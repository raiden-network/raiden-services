import os
import sqlite3

import structlog
from eth_utils import is_checksum_address

from raiden.utils.typing import BlockNumber
from raiden_libs.states import BlockchainState
from raiden_libs.types import Address

log = structlog.get_logger(__name__)


def convert_hex(raw: bytes) -> int:
    return int(raw, 16)


sqlite3.register_converter('HEX_INT', convert_hex)


def hex256(x: int) -> str:
    """Hex encodes values up to 256 bits into a fixed length

    By including this amount of leading zeros in the hex string, lexicographic
    and numeric ordering are identical. This facilitates working with these
    numbers in the database without native uint256 support.
    """
    return '0x{:064x}'.format(x)


class BaseDatabase:

    schema_filename: str

    def __init__(self, filename: str, allow_create: bool = False):
        log.info('Opening database', filename=filename)
        if filename == ':memory:':
            self.conn = sqlite3.connect(
                ':memory:',
                detect_types=sqlite3.PARSE_DECLTYPES,
                isolation_level=None,  # Disable sqlite3 module’s implicit transaction management
            )
        else:
            if os.path.dirname(filename):
                os.makedirs(os.path.dirname(filename), exist_ok=True)
            mode = 'rwc' if allow_create else 'rw'
            self.conn = sqlite3.connect(
                f'file:{filename}?mode={mode}',
                detect_types=sqlite3.PARSE_DECLTYPES,
                uri=True,
                isolation_level=None,  # Disable sqlite3 module’s implicit transaction management
            )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def _setup(
        self,
        chain_id: int,
        receiver: str,
        sync_start_block: BlockNumber,
        **contract_addresses: Address,
    ) -> None:
        """ Make sure that the db is initialized an matches the given settings """
        assert chain_id >= 0
        assert is_checksum_address(receiver)
        for contract, address in contract_addresses.items():
            assert is_checksum_address(address), f'Bad {contract}: {address}!'

        initialized = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='blockchain'"
        ).fetchone()
        settings = dict(chain_id=chain_id, receiver=receiver, **contract_addresses)

        if initialized:
            old_settings = self.conn.execute(
                f"""
                SELECT chain_id,
                       {''.join(colname + ',' for colname in contract_addresses)}
                       receiver
                FROM blockchain
            """
            ).fetchone()
            for key, val in settings.items():
                old = old_settings[key]
                assert old == val, f'DB was created with {key}={old}, got {val}!'
        else:
            # create db schema
            with open(self.schema_filename) as schema_file:
                self.conn.executescript(schema_file.read())
            update_stmt = "UPDATE blockchain SET {}".format(
                ','.join(
                    f'{key} = :{key}'
                    for key in ['chain_id', 'receiver', 'latest_known_block']
                    + list(contract_addresses)
                )
            )
            self.conn.execute(update_stmt, dict(latest_known_block=sync_start_block, **settings))

    def get_blockchain_state(self) -> BlockchainState:
        blockchain = self.conn.execute("SELECT * FROM blockchain").fetchone()
        token_network_addresses = [
            row[0] for row in self.conn.execute("SELECT address FROM token_network")
        ]
        latest_known_block = blockchain['latest_known_block']

        return BlockchainState(
            chain_id=blockchain['chain_id'],
            token_network_registry_address=blockchain['token_network_registry_address'],
            monitor_contract_address=blockchain['monitor_contract_address'],
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

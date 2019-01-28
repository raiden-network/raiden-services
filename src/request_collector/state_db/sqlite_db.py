import os
import sqlite3
from typing import Dict, Iterable, Optional

from eth_utils import is_checksum_address

# from monitoring_service.utils import BlockchainListener
from raiden_contracts.constants import ChannelState
from raiden_libs.messages import BalanceProof, MonitorRequest
from raiden_libs.types import Address, ChannelIdentifier
from raiden_libs.utils import is_channel_identifier

SCHEMA_FILENAME = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'schema.sql',
)


def convert_hex(raw: bytes) -> int:
    return int(raw, 16)


sqlite3.register_converter('HEX_INT', convert_hex)


class StateDBSqlite:
    def __init__(self, filename: str):
        self.filename = filename
        self.conn = sqlite3.connect(
            self.filename,
            isolation_level="EXCLUSIVE",
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if filename not in (None, ':memory:'):
            os.chmod(filename, 0o600)

    def setup_db(self, network_id: int, contract_address: str, receiver: str):
        """Initialize an empty database. Call this if `is_initialized()` returns False"""
        assert is_checksum_address(receiver)
        assert is_checksum_address(contract_address)
        assert network_id >= 0
        with open(SCHEMA_FILENAME) as schema_file:
            self.conn.executescript(schema_file.read())
        self.conn.execute("""
            UPDATE metadata
            SET chain_id = ?,
                monitoring_contract_address = ?,
                receiver = ?;
        """, [network_id, contract_address, receiver])
        self.conn.commit()

    def is_initialized(self) -> bool:
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'",
        )
        return cursor.fetchone() is not None

    def fetch_scalar(self, query: str, query_args: Iterable = ()):
        """ Helper function to fetch a single field of a single row """
        return self.conn.execute(query, query_args).fetchone()[0]

    def get_monitor_request_rows(
        self,
        channel_identifier: ChannelIdentifier = None,
        non_closing_signer: Address = None,
    ) -> Iterable[sqlite3.Row]:
        """ Fetch MRs from the db, optionally filtered """
        query = 'SELECT * FROM monitor_requests WHERE 1=1'  # 1=1 for easier query building
        query_args = []
        if channel_identifier:
            query += ' AND channel_identifier = ?'
            query_args.append(hex(channel_identifier))
        if non_closing_signer:
            query += ' AND non_closing_signer = ?'
            query_args.append(non_closing_signer)

        return self.conn.execute(query, query_args)

    def get_monitor_requests(
        self,
        channel_identifier: ChannelIdentifier = None,
        non_closing_signer: Address = None,
    ) -> Dict[tuple, MonitorRequest]:
        """ Return MRs keyed by (channel_id, non_closing_signer), optionally filtered """
        mr_rows = self.get_monitor_request_rows(channel_identifier, non_closing_signer)

        return {
            (x['channel_identifier'], x['non_closing_signer']): MonitorRequest(
                balance_proof=BalanceProof(
                    channel_identifier=x['channel_identifier'],
                    token_network_address=x['token_network_address'],
                    balance_hash=x['balance_hash'],
                    nonce=x['nonce'],
                    additional_hash=x['additional_hash'],
                    chain_id=self.chain_id(),
                    signature=x['closing_signature'],
                ),
                non_closing_signature=x['non_closing_signature'],
                reward_proof_signature=x['reward_proof_signature'],
                reward_amount=x['reward_amount'],
            )
            for x in mr_rows
        }

    def store_monitor_request(self, monitor_request: MonitorRequest) -> None:
        StateDBSqlite.check_monitor_request(monitor_request)
        balance_proof = monitor_request.balance_proof
        params = [
            hex(balance_proof.channel_identifier),
            monitor_request.non_closing_signer,
            balance_proof.balance_hash,
            hex(balance_proof.nonce),
            balance_proof.additional_hash,
            balance_proof.signature,
            monitor_request.non_closing_signature,
            monitor_request.reward_proof_signature,
            hex(monitor_request.reward_amount),
            balance_proof.token_network_address,
        ]
        self.conn.execute("""
            INSERT OR REPLACE INTO monitor_requests
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, params)

    @staticmethod
    def check_monitor_request(monitor_request):
        balance_proof = monitor_request.balance_proof
        assert is_channel_identifier(balance_proof.channel_identifier)
        assert is_checksum_address(balance_proof.token_network_address)

    def chain_id(self):
        return int(self.fetch_scalar("SELECT chain_id FROM metadata"))

    def server_address(self):
        return self.fetch_scalar("SELECT receiver FROM metadata")

    def monitoring_contract_address(self):
        return self.fetch_scalar("SELECT monitoring_contract_address FROM metadata")

    def get_channel(self, channel_identifier: ChannelIdentifier) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM channels WHERE channel_identifier = ?",
            [hex(channel_identifier)],
        ).fetchone()

    def store_new_channel(
        self,
        channel_identifier: ChannelIdentifier,
        token_network_address: Address,
        participant1: Address,
        participant2: Address,
    ):
        self.conn.execute("INSERT INTO channels VALUES (?, ?, ?, ?, ?)", [
            hex(channel_identifier),
            token_network_address,
            participant1,
            participant2,
            ChannelState.OPENED,
        ])

    # def save_syncstate(self, blockchain_listener: BlockchainListener):
    #     self.conn.execute("INSERT OR REPLACE INTO syncstate VALUES (?, ?, ?, ?, ?)", [
    #         blockchain_listener.contract_address,
    #         blockchain_listener.confirmed_head_number,
    #         blockchain_listener.confirmed_head_hash,
    #         blockchain_listener.unconfirmed_head_number,
    #         blockchain_listener.unconfirmed_head_hash,
    #     ])

    def load_syncstate(self, contract_address: Address) -> Optional[Dict]:
        return self.conn.execute(
            "SELECT * FROM syncstate WHERE contract_address = ?",
            [contract_address],
        ).fetchone()

    def get_synced_contracts(self) -> Iterable[Address]:
        return [
            row['contract_address']
            for row in self.conn.execute("SELECT contract_address FROM syncstate")
        ]

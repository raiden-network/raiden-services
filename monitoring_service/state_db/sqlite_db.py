import os
import sqlite3
from typing import Dict, Iterable, List

from eth_utils import is_checksum_address

from raiden_libs.messages import BalanceProof, MonitorRequest
from raiden_libs.types import Address, ChannelIdentifier
from raiden_libs.utils import is_channel_identifier

from .queries import ADD_MONITOR_REQUEST_SQL, DB_CREATION_SQL, UPDATE_METADATA_SQL


class StateDBSqlite:
    def __init__(self, filename: str):
        self.filename = filename
        self.conn = sqlite3.connect(self.filename, isolation_level="EXCLUSIVE")
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
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

    def is_initialized(self) -> bool:
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'",
        )
        return self.cursor.fetchone() is not None

    def fetch_scalar(self, query: str, query_args: Iterable = ()):
        """ Helper function to fetch a single field of a single row """
        self.cursor.execute(query, query_args)
        return self.cursor.fetchone()[0]

    def get_monitor_request_rows(
        self,
        channel_identifier: ChannelIdentifier = None,
        non_closing_signer: Address = None,
    ) -> List[dict]:
        """ Fetch MRs from the db, optionally filtered """
        query = 'SELECT * FROM monitor_requests WHERE 1=1'  # 1=1 for easier query building
        query_args = []
        if channel_identifier:
            query += ' AND channel_identifier = ?'
            query_args.append(hex(channel_identifier))
        if non_closing_signer:
            query += ' AND non_closing_signer = ?'
            query_args.append(non_closing_signer)

        self.cursor.execute(query, query_args)
        ret = []
        for x in self.cursor:
            x = dict(x)
            for hex_key in ['reward_amount', 'nonce', 'channel_identifier']:
                x[hex_key] = int(x[hex_key], 16)
            ret.append(x)

        return ret

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
                # Monitor address is not used, but required for now, see
                # https://github.com/raiden-network/raiden-monitoring-service/issues/42
                monitor_address='0x' + '0' * 40,
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
        self.conn.execute(ADD_MONITOR_REQUEST_SQL, params)

    def delete_monitor_request(self, channel_id: ChannelIdentifier) -> None:
        """ Delete all MRs for the given channel """
        assert is_channel_identifier(channel_id)
        self.cursor.execute(
            'DELETE FROM monitor_requests WHERE channel_identifier = ?',
            [channel_id],
        )

    @staticmethod
    def check_monitor_request(monitor_request):
        balance_proof = monitor_request.balance_proof
        assert is_channel_identifier(balance_proof.channel_identifier)
        assert is_checksum_address(balance_proof.token_network_address)
        assert is_checksum_address(monitor_request.monitor_address)

    def chain_id(self):
        return int(self.fetch_scalar("SELECT chain_id FROM metadata"))

    def server_address(self):
        return self.fetch_scalar("SELECT receiver FROM metadata")

    def monitoring_contract_address(self):
        return self.fetch_scalar("SELECT monitoring_contract_address FROM metadata")

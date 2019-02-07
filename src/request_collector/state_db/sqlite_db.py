import sqlite3
from typing import Dict, Iterable, Optional
import json

from eth_utils import is_checksum_address

from monitoring_service.database import BaseDatabase
from raiden_contracts.constants import ChannelState
from raiden_libs.messages import BalanceProof, MonitorRequest
from raiden_libs.types import Address, ChannelIdentifier
from raiden_libs.utils import is_channel_identifier


def convert_hex(raw: bytes) -> int:
    return int(raw, 16)


sqlite3.register_converter('HEX_INT', convert_hex)
sqlite3.register_converter('JSON', json.loads)


def adapt_tuple(t: tuple) -> str:
    return json.dumps(t)


sqlite3.register_adapter(tuple, adapt_tuple)


class StateDBSqlite(BaseDatabase):
    def __init__(self, filename: str = None, conn=None):
        if filename:
            assert conn is None
            super(StateDBSqlite, self).__init__(filename)
        else:
            # for test fixture only
            assert conn
            self.conn = conn

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
            hex(monitor_request.reward_amount),  # type: ignore
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
        return int(self.fetch_scalar("SELECT chain_id FROM blockchain"))

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

import sqlite3
from typing import Optional, List
import dataclasses
import os

from eth_utils import is_checksum_address

from monitoring_service.states import (
    Channel, MonitoringServiceState, MonitorRequest, BlockchainState, OnChainUpdateStatus,
)

SCHEMA_FILENAME = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'schema.sql',
)


class BaseDatabase:

    def __init__(self, filename: str):
        self.conn = sqlite3.connect(
            filename,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def upsert_monitor_request(self, request: MonitorRequest) -> None:
        values = [
            hex(request.channel_identifier),
            request.token_network_address,
            request.balance_hash,
            hex(request.nonce),
            request.additional_hash,
            request.closing_signature,
            request.non_closing_signature,
            hex(request.reward_amount),
            request.reward_proof_signature,
            request.non_closing_signer,
        ]
        upsert_sql = "INSERT OR REPLACE INTO monitor_request VALUES ({})".format(
            ', '.join('?' * len(values)),
        )
        self.conn.execute(upsert_sql, values)

    def get_monitor_request(
            self,
            token_network_address: str,
            channel_id: int,
            non_closing_signer: str,
    ) -> Optional[MonitorRequest]:
        row = self.conn.execute(
            """
                SELECT * FROM monitor_request
                WHERE channel_identifier = ?
                  AND token_network_address = ?
                  AND non_closing_signer = ?
            """,
            [hex(channel_id), token_network_address, non_closing_signer],
        ).fetchone()
        if row is None:
            return None

        kwargs = {
            key: val for key, val in zip(row.keys(), row)
            if key in [f.name for f in dataclasses.fields(MonitorRequest)]
        }
        mr = MonitorRequest(chain_id=1, **kwargs)
        return mr

    def monitor_request_count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM monitor_request").fetchone()[0]


class Database(BaseDatabase):
    """ Holds all MS state which can't be quickly regenerated after a crash/shutdown """

    def __init__(
        self,
        filename: str,
        chain_id: int,
        msc_address: str,
        registry_address: str,
        receiver: str,
    ) -> None:
        super(Database, self).__init__(filename)
        self._setup(chain_id, msc_address, registry_address, receiver)

    def _setup(
        self,
        chain_id: int,
        msc_address: str,
        registry_address: str,
        receiver: str,
    ) -> None:
        """ Make sure that the db is initialized an matches the given settings """
        assert chain_id >= 0
        assert is_checksum_address(msc_address)
        assert is_checksum_address(registry_address)
        assert is_checksum_address(receiver)

        initialized = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='blockchain'",
        ).fetchone()
        settings = [chain_id, msc_address, registry_address, receiver]

        if initialized:
            old_settings = self.conn.execute("""
                SELECT chain_id,
                       monitor_contract_address,
                       token_network_registry_address,
                       receiver
                FROM blockchain
            """).fetchone()
            assert tuple(old_settings) == settings, f"{tuple(old_settings)} != {settings}"
        else:
            with self.conn:
                # create db schema
                with open(SCHEMA_FILENAME) as schema_file:
                    self.conn.executescript(schema_file.read())
                self.conn.execute("""
                    UPDATE blockchain
                    SET chain_id = ?,
                        monitor_contract_address = ?,
                        token_network_registry_address = ?,
                        receiver = ?;
                """, settings)

    def upsert_channel(self, channel: Channel) -> None:
        values = [
            channel.token_network_address,
            hex(channel.identifier),
            channel.participant1,
            channel.participant2,
            channel.settle_timeout,
            channel.state,
            channel.closing_block,
            channel.closing_participant,
            channel.closing_tx_hash,
            channel.claim_tx_hash,
            dataclasses.astuple(channel.update_status) if channel.update_status else None,
        ]
        with self.conn:
            upsert_sql = "INSERT OR REPLACE INTO channel VALUES ({})".format(
                ', '.join('?' * len(values)),
            )
            self.conn.execute(upsert_sql, values)

    def get_channel(self, token_network_address: str, channel_id: int) -> Optional[Channel]:
        row = self.conn.execute(
            """
                SELECT * FROM channel
                WHERE identifier = ? AND token_network_address = ?
            """,
            [hex(channel_id), token_network_address],
        ).fetchone()

        if row is None:
            return None
        row = list(row)
        if row[-1] is not None:
            row[-1] = OnChainUpdateStatus(*row[-1])
        return Channel(*row)

    def channel_count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM channel").fetchone()[0]

    def update_state(self, state: MonitoringServiceState) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE blockchain SET latest_known_block = ?",
                [state.blockchain_state.latest_known_block],
            )
            self.conn.execute("DELETE FROM token_network")
            self.conn.executemany(
                "INSERT INTO token_network VALUES (?)",
                [[address] for address in state.blockchain_state.token_network_addresses],
            )

    def load_state(self, sync_start_block: int) -> MonitoringServiceState:
        """ Load MS state from db or return a new empty state if not saved one is present

        An empty state is initialized with `latest_known_block =
        sync_start_block - 1`. If a saved state is present, `sync_start_block`
        is ignored.
        """
        blockchain = self.conn.execute("SELECT * FROM blockchain").fetchone()
        if blockchain['latest_known_block'] is None:
            # state has never been saved, initialize a new state
            token_network_addresses: List[str] = []
            latest_known_block = sync_start_block - 1
        else:
            token_network_addresses = [
                row[0] for row in self.conn.execute("SELECT address FROM token_network")
            ]
            latest_known_block = blockchain['latest_known_block']

        chain_state = BlockchainState(
            token_network_registry_address=blockchain['token_network_registry_address'],
            monitor_contract_address=blockchain['monitor_contract_address'],
            latest_known_block=latest_known_block,
            token_network_addresses=token_network_addresses,
        )
        ms_state = MonitoringServiceState(
            blockchain_state=chain_state,
            address=blockchain['receiver'],
        )
        return ms_state

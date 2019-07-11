import os
import sqlite3
from typing import List, Optional, Union, cast

import structlog
from eth_utils import decode_hex, encode_hex, to_canonical_address, to_checksum_address, to_hex

from monitoring_service.events import (
    ActionClaimRewardTriggeredEvent,
    ActionMonitoringTriggeredEvent,
    ScheduledEvent,
)
from monitoring_service.states import (
    Channel,
    MonitoringServiceState,
    MonitorRequest,
    OnChainUpdateStatus,
)
from raiden.utils.typing import (
    Address,
    BlockNumber,
    ChainID,
    ChannelID,
    TokenNetworkAddress,
    TransactionHash,
)
from raiden_libs.database import BaseDatabase, hex256

SubEvent = Union[ActionMonitoringTriggeredEvent, ActionClaimRewardTriggeredEvent]

log = structlog.get_logger(__name__)
EVENT_ID_TYPE_MAP = {0: ActionMonitoringTriggeredEvent, 1: ActionClaimRewardTriggeredEvent}
EVENT_TYPE_ID_MAP = {v: k for k, v in EVENT_ID_TYPE_MAP.items()}


class SharedDatabase(BaseDatabase):
    """ DB shared by MS and request collector """

    schema_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "schema.sql")

    def upsert_monitor_request(self, request: MonitorRequest) -> None:
        self.upsert(
            "monitor_request",
            dict(
                channel_identifier=hex256(request.channel_identifier),
                token_network_address=to_checksum_address(request.token_network_address),
                balance_hash=request.balance_hash,
                nonce=hex256(request.nonce),
                additional_hash=request.additional_hash,
                closing_signature=to_hex(request.closing_signature),
                non_closing_signature=to_hex(request.non_closing_signature),
                reward_amount=hex256(request.reward_amount),
                reward_proof_signature=to_hex(request.reward_proof_signature),
                non_closing_signer=to_checksum_address(request.non_closing_signer),
            ),
        )

    def get_monitor_request(
        self,
        token_network_address: TokenNetworkAddress,
        channel_id: ChannelID,
        non_closing_signer: Address,
    ) -> Optional[MonitorRequest]:
        row = self.conn.execute(
            """
                SELECT monitor_request.*,
                    blockchain.chain_id,
                    blockchain.monitor_contract_address AS msc_address
                FROM monitor_request,
                    blockchain
                WHERE channel_identifier = ?
                  AND token_network_address = ?
                  AND non_closing_signer = ?
            """,
            [
                hex256(channel_id),
                to_checksum_address(token_network_address),
                to_checksum_address(non_closing_signer),
            ],
        ).fetchone()
        if row is None:
            return None

        kwargs = {
            key: val
            for key, val in zip(row.keys(), row)
            if key not in ("non_closing_signer", "saved_at", "waiting_for_channel")
        }
        kwargs["token_network_address"] = to_canonical_address(kwargs["token_network_address"])
        kwargs["msc_address"] = to_canonical_address(kwargs["msc_address"])
        kwargs["closing_signature"] = decode_hex(kwargs["closing_signature"])
        kwargs["non_closing_signature"] = decode_hex(kwargs["non_closing_signature"])
        kwargs["reward_proof_signature"] = decode_hex(kwargs["reward_proof_signature"])
        return MonitorRequest(**kwargs)

    def monitor_request_count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM monitor_request").fetchone()[0]

    def upsert_channel(self, channel: Channel) -> None:
        values = [
            to_checksum_address(channel.token_network_address),
            hex256(channel.identifier),
            to_checksum_address(channel.participant1),
            to_checksum_address(channel.participant2),
            hex256(channel.settle_timeout),
            channel.state,
            hex256(channel.closing_block) if channel.closing_block else None,
            channel.closing_participant,
            encode_hex(channel.closing_tx_hash) if channel.closing_tx_hash else None,
            encode_hex(channel.claim_tx_hash) if channel.claim_tx_hash else None,
        ]
        if channel.update_status:
            values += [
                to_checksum_address(channel.update_status.update_sender_address),
                hex256(channel.update_status.nonce),
            ]
        else:
            values += [None, None]

        upsert_sql = "INSERT OR REPLACE INTO channel VALUES ({})".format(
            ", ".join("?" * len(values))
        )
        self.conn.execute(upsert_sql, values)

    def get_channel(
        self, token_network_address: TokenNetworkAddress, channel_id: ChannelID
    ) -> Optional[Channel]:
        row = self.conn.execute(
            """
                SELECT * FROM channel
                WHERE identifier = ? AND token_network_address = ?
            """,
            [hex256(channel_id), to_checksum_address(token_network_address)],
        ).fetchone()

        if row is None:
            return None
        kwargs = {
            key: val for key, val in zip(row.keys(), row) if not key.startswith("update_status")
        }
        kwargs["token_network_address"] = decode_hex(kwargs["token_network_address"])
        kwargs["participant1"] = decode_hex(kwargs["participant1"])
        kwargs["participant2"] = decode_hex(kwargs["participant2"])
        if kwargs["closing_tx_hash"] is not None:
            kwargs["closing_tx_hash"] = decode_hex(kwargs["closing_tx_hash"])
        if kwargs["claim_tx_hash"] is not None:
            kwargs["claim_tx_hash"] = decode_hex(kwargs["claim_tx_hash"])

        return Channel(
            update_status=OnChainUpdateStatus(
                update_sender_address=decode_hex(row["update_status_sender"]),
                nonce=row["update_status_nonce"],
            )
            if row["update_status_nonce"] is not None
            else None,
            **kwargs,
        )

    def channel_count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM channel").fetchone()[0]

    def upsert_scheduled_event(self, event: ScheduledEvent) -> None:
        contained_event: SubEvent = cast(SubEvent, event.event)
        values = [
            hex256(event.trigger_block_number),
            EVENT_TYPE_ID_MAP[type(contained_event)],
            to_checksum_address(contained_event.token_network_address),
            hex256(contained_event.channel_identifier),
            contained_event.non_closing_participant,
        ]
        upsert_sql = "INSERT OR REPLACE INTO scheduled_events VALUES ({})".format(
            ", ".join("?" * len(values))
        )
        self.conn.execute(upsert_sql, values)

    def get_scheduled_events(self, max_trigger_block: BlockNumber) -> List[ScheduledEvent]:
        rows = self.conn.execute(
            """
                SELECT * FROM scheduled_events
                WHERE trigger_block_number <= ?
            """,
            [hex256(max_trigger_block)],
        ).fetchall()

        def create_scheduled_event(row: sqlite3.Row) -> ScheduledEvent:
            event_type = EVENT_ID_TYPE_MAP[row["event_type"]]
            sub_event = event_type(
                decode_hex(row["token_network_address"]),
                row["channel_identifier"],
                row["non_closing_participant"],
            )

            return ScheduledEvent(
                trigger_block_number=row["trigger_block_number"], event=sub_event
            )

        return [create_scheduled_event(row) for row in rows]

    def remove_scheduled_event(self, event: ScheduledEvent) -> None:
        contained_event: SubEvent = cast(SubEvent, event.event)
        values = [
            hex256(event.trigger_block_number),
            to_checksum_address(contained_event.token_network_address),
            hex256(contained_event.channel_identifier),
            contained_event.non_closing_participant,
        ]
        self.conn.execute(
            """
                DELETE FROM scheduled_events
                WHERE trigger_block_number = ?
                    AND token_network_address = ?
                    AND channel_identifier = ?
                    AND non_closing_participant =?
            """,
            values,
        )

    def scheduled_event_count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM scheduled_events").fetchone()[0]

    def get_waiting_transactions(self) -> List[TransactionHash]:
        return [
            TransactionHash(decode_hex(row[0]))
            for row in self.conn.execute("SELECT transaction_hash FROM waiting_transactions")
        ]

    def add_waiting_transaction(self, waiting_tx_hash: TransactionHash) -> None:
        self.conn.execute(
            "INSERT INTO waiting_transactions VALUES (?)", [encode_hex(waiting_tx_hash)]
        )

    def remove_waiting_transaction(self, tx_hash: TransactionHash) -> None:
        self.conn.execute(
            "DELETE FROM waiting_transactions WHERE transaction_hash = ?", [encode_hex(tx_hash)]
        )

    def load_state(self) -> MonitoringServiceState:
        """ Load MS state from db or return a new empty state if not saved one is present
        """
        blockchain = self.conn.execute("SELECT * FROM blockchain").fetchone()
        ms_state = MonitoringServiceState(
            blockchain_state=self.get_blockchain_state(),
            address=decode_hex(blockchain["receiver"]),
        )
        return ms_state


class Database(SharedDatabase):
    """ Holds all MS state which can't be quickly regenerated after a crash/shutdown """

    def __init__(
        self,
        filename: str,
        chain_id: ChainID,
        msc_address: Address,
        registry_address: Address,
        receiver: Address,
        sync_start_block: BlockNumber = BlockNumber(0),
    ) -> None:
        super(Database, self).__init__(filename, allow_create=True)
        self._setup(
            chain_id=chain_id,
            monitor_contract_address=msc_address,
            token_network_registry_address=registry_address,
            receiver=receiver,
            sync_start_block=sync_start_block,
        )

import os
import sqlite3
from typing import List, Optional, Union, cast

import structlog
from eth_utils import is_checksum_address

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
from raiden.utils.typing import BlockNumber
from raiden_libs.database import BaseDatabase
from raiden_libs.types import Address

SubEvent = Union[ActionMonitoringTriggeredEvent, ActionClaimRewardTriggeredEvent]

log = structlog.get_logger(__name__)
EVENT_ID_TYPE_MAP = {0: ActionMonitoringTriggeredEvent, 1: ActionClaimRewardTriggeredEvent}
EVENT_TYPE_ID_MAP = {v: k for k, v in EVENT_ID_TYPE_MAP.items()}


class SharedDatabase(BaseDatabase):
    """ DB shared by MS and request collector """

    schema_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "schema.sql")

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
            ", ".join("?" * len(values))
        )
        self.conn.execute(upsert_sql, values)

    def get_monitor_request(
        self, token_network_address: str, channel_id: int, non_closing_signer: str
    ) -> Optional[MonitorRequest]:
        assert is_checksum_address(token_network_address)
        assert is_checksum_address(non_closing_signer)
        row = self.conn.execute(
            """
                SELECT *,
                    (SELECT chain_id FROM blockchain) As chain_id
                FROM monitor_request
                WHERE channel_identifier = ?
                  AND token_network_address = ?
                  AND non_closing_signer = ?
            """,
            [hex(channel_id), token_network_address, non_closing_signer],
        ).fetchone()
        if row is None:
            return None

        kwargs = {key: val for key, val in zip(row.keys(), row) if key != "non_closing_signer"}
        mr = MonitorRequest(**kwargs)
        return mr

    def monitor_request_count(self) -> int:
        return self.conn.execute("SELECT count(*) FROM monitor_request").fetchone()[0]

    def upsert_channel(self, channel: Channel) -> None:
        values = [
            channel.token_network_address,
            hex(channel.identifier),
            channel.participant1,
            channel.participant2,
            hex(channel.settle_timeout),
            channel.state,
            hex(channel.closing_block) if channel.closing_block else None,
            channel.closing_participant,
            channel.closing_tx_hash,
            channel.claim_tx_hash,
        ]
        if channel.update_status:
            values += [
                channel.update_status.update_sender_address,
                hex(channel.update_status.nonce),
            ]
        else:
            values += [None, None]

        upsert_sql = "INSERT OR REPLACE INTO channel VALUES ({})".format(
            ", ".join("?" * len(values))
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
        kwargs = {
            key: val for key, val in zip(row.keys(), row) if not key.startswith("update_status")
        }
        return Channel(
            update_status=OnChainUpdateStatus(
                update_sender_address=row["update_status_sender"], nonce=row["update_status_nonce"]
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
            hex(event.trigger_block_number),
            EVENT_TYPE_ID_MAP[type(contained_event)],
            contained_event.token_network_address,
            hex(contained_event.channel_identifier),
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
            [hex(max_trigger_block)],
        ).fetchall()

        def create_scheduled_event(row: sqlite3.Row) -> ScheduledEvent:
            event_type = EVENT_ID_TYPE_MAP[row["event_type"]]
            sub_event = event_type(
                row["token_network_address"],
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
            hex(event.trigger_block_number),
            contained_event.token_network_address,
            hex(contained_event.channel_identifier),
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

    def get_waiting_transactions(self) -> List[str]:
        return [
            row[0]
            for row in self.conn.execute("SELECT transaction_hash FROM waiting_transactions")
        ]

    def add_waiting_transaction(self, waiting_tx_hash: str) -> None:
        self.conn.execute("INSERT INTO waiting_transactions VALUES (?)", [waiting_tx_hash])

    def remove_waiting_transaction(self, tx_hash: str) -> None:
        self.conn.execute("DELETE FROM waiting_transactions WHERE transaction_hash = ?", [tx_hash])

    def load_state(self) -> MonitoringServiceState:
        """ Load MS state from db or return a new empty state if not saved one is present
        """
        blockchain = self.conn.execute("SELECT * FROM blockchain").fetchone()
        ms_state = MonitoringServiceState(
            blockchain_state=self.get_blockchain_state(), address=blockchain["receiver"]
        )
        return ms_state


class Database(SharedDatabase):
    """ Holds all MS state which can't be quickly regenerated after a crash/shutdown """

    def __init__(
        self,
        filename: str,
        chain_id: int,
        msc_address: Address,
        registry_address: Address,
        receiver: str,
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

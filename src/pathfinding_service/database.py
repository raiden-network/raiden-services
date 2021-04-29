import json
import os
from datetime import datetime
from typing import Dict, Iterator, List, Optional, Tuple
from uuid import UUID

import structlog
from eth_utils import to_canonical_address, to_checksum_address

from pathfinding_service.model import IOU
from pathfinding_service.model.channel import Channel
from pathfinding_service.model.feedback import FeedbackToken
from pathfinding_service.model.token_network import TokenNetwork
from pathfinding_service.typing import DeferableMessage
from raiden.messages.path_finding_service import PFSCapacityUpdate
from raiden.storage.serialization.serializer import JSONSerializer
from raiden.utils.typing import (
    Address,
    BlockNumber,
    ChainID,
    ChannelID,
    FeeAmount,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_libs.database import BaseDatabase, hex256

log = structlog.get_logger(__name__)


class PFSDatabase(BaseDatabase):
    """Store data that needs to persist between PFS restarts"""

    schema_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "schema.sql")

    def __init__(
        self,
        filename: str,
        chain_id: ChainID,
        pfs_address: Address,
        sync_start_block: BlockNumber = BlockNumber(0),
        allow_create: bool = False,
        **contract_addresses: Address,
    ):
        super().__init__(filename, allow_create=allow_create)
        self.pfs_address = pfs_address

        # Keep the journal around and skip inode updates.
        # References:
        # https://sqlite.org/atomiccommit.html#_persistent_rollback_journals
        # https://sqlite.org/pragma.html#pragma_journal_mode
        self.conn.execute("PRAGMA journal_mode=PERSIST")

        self._setup(
            chain_id=chain_id,
            receiver=pfs_address,
            sync_start_block=sync_start_block,
            **contract_addresses,
        )

    def upsert_capacity_update(self, message: PFSCapacityUpdate) -> None:
        capacity_update_dict = dict(
            updating_participant=to_checksum_address(message.updating_participant),
            token_network_address=to_checksum_address(
                message.canonical_identifier.token_network_address
            ),
            channel_id=hex256(message.canonical_identifier.channel_identifier),
            updating_capacity=hex256(message.updating_capacity),
            other_capacity=hex256(message.other_capacity),
        )
        self.upsert("capacity_update", capacity_update_dict)

    def get_capacity_updates(
        self,
        updating_participant: Address,
        token_network_address: TokenNetworkAddress,
        channel_id: int,
    ) -> Tuple[TokenAmount, TokenAmount]:
        capacity_list = self.conn.execute(
            """
            SELECT updating_capacity, other_capacity
            FROM capacity_update WHERE updating_participant=?
            AND token_network_address=?
            AND channel_id=?
        """,
            [
                to_checksum_address(updating_participant),
                to_checksum_address(token_network_address),
                hex256(channel_id),
            ],
        )
        try:
            return next(capacity_list)
        except StopIteration:
            return TokenAmount(0), TokenAmount(0)

    def get_latest_committed_block(self) -> BlockNumber:
        return self.conn.execute("SELECT latest_committed_block FROM blockchain").fetchone()[0]

    def update_lastest_committed_block(self, latest_committed_block: BlockNumber) -> None:
        log.info("Updating latest_committed_block", latest_committed_block=latest_committed_block)
        self.conn.execute(
            "UPDATE blockchain SET latest_committed_block = ?", [latest_committed_block]
        )

    def upsert_iou(self, iou: IOU) -> None:
        iou_dict = IOU.Schema(exclude=["receiver", "chain_id"]).dump(iou)
        iou_dict["one_to_n_address"] = to_checksum_address(iou_dict["one_to_n_address"])
        for key in ("amount", "expiration_block"):
            iou_dict[key] = hex256(int(iou_dict[key]))
        self.upsert("iou", iou_dict)

    def get_ious(
        self,
        sender: Optional[Address] = None,
        expiration_block: Optional[BlockNumber] = None,
        claimed: Optional[bool] = None,
        expires_after: Optional[BlockNumber] = None,
        expires_before: Optional[BlockNumber] = None,
        amount_at_least: Optional[TokenAmount] = None,
    ) -> Iterator[IOU]:
        query = """
            SELECT *, (SELECT chain_id FROM blockchain) AS chain_id
            FROM iou
            WHERE 1=1
        """
        args: list = []
        if sender is not None:
            query += " AND sender = ?"
            args.append(to_checksum_address(sender))
        if expiration_block is not None:
            query += " AND expiration_block = ?"
            args.append(hex256(expiration_block))
        if claimed is not None:
            query += " AND claimed = ?"
            args.append(claimed)
        if expires_before is not None:
            query += " AND expiration_block < ?"
            args.append(hex256(expires_before))
        if expires_after is not None:
            query += " AND expiration_block > ?"
            args.append(hex256(expires_after))
        if amount_at_least is not None:
            query += " AND amount >= ?"
            args.append(hex256(amount_at_least))

        for row in self.conn.execute(query, args):
            iou_dict = dict(zip(row.keys(), row))
            iou_dict["receiver"] = to_checksum_address(self.pfs_address)
            yield IOU.Schema().load(iou_dict)

    def get_nof_claimed_ious(self) -> int:
        query = """
            SELECT COUNT(*)
            FROM iou
            where claimed
        """
        result = self.conn.execute(query)
        nof_claimed_ious = result.fetchone()
        assert result.fetchone() is None
        return nof_claimed_ious["COUNT(*)"]

    def get_iou(
        self,
        sender: Address,
        expiration_block: Optional[BlockNumber] = None,
        claimed: Optional[bool] = None,
    ) -> Optional[IOU]:
        try:
            return next(self.get_ious(sender, expiration_block, claimed))
        except StopIteration:
            return None

    def upsert_channel(self, channel: Channel) -> None:
        channel_dict = Channel.Schema().dump(channel)
        for key in (
            "channel_id",
            "settle_timeout",
            "capacity1",
            "reveal_timeout1",
            "update_nonce1",
            "capacity2",
            "reveal_timeout2",
            "update_nonce2",
        ):
            channel_dict[key] = hex256(int(channel_dict[key]))
        channel_dict["fee_schedule1"] = json.dumps(channel_dict["fee_schedule1"])
        channel_dict["fee_schedule2"] = json.dumps(channel_dict["fee_schedule2"])
        self.upsert("channel", channel_dict)

    def get_channels(self) -> Iterator[Channel]:
        for row in self.conn.execute("SELECT * FROM channel"):
            channel_dict = dict(zip(row.keys(), row))
            channel_dict["fee_schedule1"] = json.loads(channel_dict["fee_schedule1"])
            channel_dict["fee_schedule2"] = json.loads(channel_dict["fee_schedule2"])
            yield Channel.Schema().load(channel_dict)

    def delete_channel(
        self, token_network_address: TokenNetworkAddress, channel_id: ChannelID
    ) -> bool:
        """Tries to delete a channel from the database

        Args:
            token_network_address: The address of the token network of the channel
            channel_id: The id of the channel

        Returns: `True` if the channel was deleted, `False` if it did not exist
        """
        cursor = self.conn.execute(
            "DELETE FROM channel WHERE token_network_address = ? AND channel_id = ?",
            [to_checksum_address(token_network_address), hex256(channel_id)],
        )
        assert cursor.rowcount <= 1, "Did delete more than one channel"

        return cursor.rowcount == 1

    def get_token_networks(self) -> Iterator[TokenNetwork]:
        for row in self.conn.execute("SELECT address FROM token_network"):
            yield TokenNetwork(
                token_network_address=TokenNetworkAddress(to_canonical_address(row[0]))
            )

    def prepare_feedback(
        self, token: FeedbackToken, route: List[Address], estimated_fee: FeeAmount
    ) -> None:
        hexed_route = [to_checksum_address(e) for e in route]
        token_dict = dict(
            token_id=token.uuid.hex,
            creation_time=token.creation_time,
            token_network_address=to_checksum_address(token.token_network_address),
            route=json.dumps(hexed_route),
            estimated_fee=hex256(estimated_fee),
            source_address=hexed_route[0],
            target_address=hexed_route[-1],
        )
        self.insert("feedback", token_dict)

    def update_feedback(self, token: FeedbackToken, route: List[Address], successful: bool) -> int:
        hexed_route = [to_checksum_address(e) for e in route]
        token_dict = dict(
            token_id=token.uuid.hex,
            token_network_address=to_checksum_address(token.token_network_address),
            route=json.dumps(hexed_route),
            successful=successful,
            feedback_time=datetime.utcnow(),
        )
        updated_rows = self.conn.execute(
            """
            UPDATE feedback
            SET
                successful = :successful,
                feedback_time = :feedback_time
            WHERE
                token_id = :token_id AND
                token_network_address = :token_network_address AND
                route = :route AND
                successful IS NULL;
        """,
            token_dict,
        ).rowcount

        return updated_rows

    def get_feedback_routes(
        self,
        token_network_address: TokenNetworkAddress,
        source_address: Address,
        target_address: Optional[Address] = None,
    ) -> Iterator[Dict]:
        filters = {
            "token_network_address": to_checksum_address(token_network_address),
            "source_address": to_checksum_address(source_address),
        }

        where_clause = ""
        if target_address:
            where_clause = " AND target_address = :target_address"
            filters["target_address"] = to_checksum_address(target_address)

        sql = f"""
            SELECT
                source_address, target_address, route, estimated_fee, token_id
            FROM
                feedback
            WHERE
                token_network_address = :token_network_address AND
                source_address = :source_address
                {where_clause}
        """

        for row in self.conn.execute(sql, filters):
            route = dict(zip(row.keys(), row))
            route["route"] = json.loads(route["route"])
            yield route

    def get_feedback_token(
        self, token_id: UUID, token_network_address: TokenNetworkAddress, route: List[Address]
    ) -> Optional[FeedbackToken]:
        hexed_route = [to_checksum_address(e) for e in route]
        token = self.conn.execute(
            """SELECT * FROM feedback WHERE
                token_id = ? AND
                token_network_address = ? AND
                route = ?;
            """,
            [token_id.hex, to_checksum_address(token_network_address), json.dumps(hexed_route)],
        ).fetchone()

        if token:
            return FeedbackToken(
                token_network_address=TokenNetworkAddress(
                    to_canonical_address(token["token_network_address"])
                ),
                uuid=UUID(token["token_id"]),
                creation_time=token["creation_time"],
            )

        return None

    def get_num_routes_feedback(
        self, only_with_feedback: bool = False, only_successful: bool = False
    ) -> int:
        where_clause = ""
        if only_with_feedback:
            where_clause = "WHERE successful IS NOT NULL"
        elif only_successful:
            where_clause = "WHERE successful"

        return self.conn.execute(f"SELECT COUNT(*) FROM feedback {where_clause};").fetchone()[0]

    def insert_waiting_message(self, message: DeferableMessage) -> None:
        self.insert(
            "waiting_message",
            dict(
                token_network_address=to_checksum_address(
                    message.canonical_identifier.token_network_address
                ),
                channel_id=hex256(message.canonical_identifier.channel_identifier),
                message=JSONSerializer.serialize(message),
            ),
        )

    def pop_waiting_messages(
        self, token_network_address: TokenNetworkAddress, channel_id: ChannelID
    ) -> Iterator[DeferableMessage]:
        """Return all waiting messages for the given channel and delete them from the db"""
        # Return messages
        for row in self.conn.execute(
            """
            SELECT message FROM waiting_message
            WHERE token_network_address = ? AND channel_id = ?
            """,
            [to_checksum_address(token_network_address), hex256(channel_id)],
        ):
            yield JSONSerializer.deserialize(row["message"])

        # Delete returned messages
        self.conn.execute(
            "DELETE FROM waiting_message WHERE token_network_address = ? AND channel_id = ?",
            [to_checksum_address(token_network_address), hex256(channel_id)],
        )

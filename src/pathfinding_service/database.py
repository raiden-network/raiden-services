import json
import os
from datetime import datetime
from typing import Iterator, List, Optional, Tuple
from uuid import UUID

import structlog
from eth_utils import decode_hex, to_checksum_address

from pathfinding_service.model import IOU
from pathfinding_service.model.channel_view import ChannelView
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
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_libs.database import BaseDatabase, hex256

log = structlog.get_logger(__name__)


class PFSDatabase(BaseDatabase):
    """ Store data that needs to persist between PFS restarts """

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
        super(PFSDatabase, self).__init__(filename, allow_create=allow_create)
        self.pfs_address = pfs_address
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

    def get_latest_known_block(self) -> BlockNumber:
        return self.conn.execute("SELECT latest_known_block FROM blockchain").fetchone()[0]

    def update_lastest_known_block(self, latest_known_block: BlockNumber) -> None:
        self.conn.execute("UPDATE blockchain SET latest_known_block = ?", [latest_known_block])

    def upsert_iou(self, iou: IOU) -> None:
        iou_dict = IOU.Schema(exclude=["receiver", "chain_id"]).dump(iou)
        iou_dict["one_to_n_address"] = to_checksum_address(iou_dict["one_to_n_address"])
        for key in ("amount", "expiration_block"):
            iou_dict[key] = hex256(iou_dict[key])
        self.upsert("iou", iou_dict)

    def get_ious(
        self,
        sender: Address = None,
        expiration_block: BlockNumber = None,
        claimed: bool = None,
        expires_before: BlockNumber = None,
        amount_at_least: TokenAmount = None,
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
        if amount_at_least is not None:
            query += " AND amount >= ?"
            args.append(hex256(amount_at_least))

        for row in self.conn.execute(query, args):
            iou_dict = dict(zip(row.keys(), row))
            iou_dict["receiver"] = to_checksum_address(self.pfs_address)
            yield IOU.Schema().load(iou_dict)

    def get_iou(
        self, sender: Address, expiration_block: BlockNumber = None, claimed: bool = None
    ) -> Optional[IOU]:
        try:
            return next(self.get_ious(sender, expiration_block, claimed))
        except StopIteration:
            return None

    def upsert_channel_view(self, channel_view: ChannelView) -> None:
        cv_dict = ChannelView.Schema().dump(channel_view)
        for key in (
            "channel_id",
            "settle_timeout",
            "capacity",
            "reveal_timeout",
            "deposit",
            "update_nonce",
        ):
            cv_dict[key] = hex256(cv_dict[key])
        cv_dict["fee_schedule_sender"] = json.dumps(cv_dict["fee_schedule_sender"])
        cv_dict["fee_schedule_receiver"] = json.dumps(cv_dict["fee_schedule_receiver"])
        self.upsert("channel_view", cv_dict)

    def get_channel_views(self) -> Iterator[ChannelView]:
        query = "SELECT * FROM channel_view"
        for row in self.conn.execute(query):
            cv_dict = dict(zip(row.keys(), row))
            cv_dict["fee_schedule_sender"] = json.loads(cv_dict["fee_schedule_sender"])
            cv_dict["fee_schedule_receiver"] = json.loads(cv_dict["fee_schedule_receiver"])
            yield ChannelView.Schema().load(cv_dict)

    def delete_channel_views(self, channel_id: ChannelID) -> None:
        self.conn.execute("DELETE FROM channel_view WHERE channel_id = ?", [channel_id])

    def get_token_networks(self) -> Iterator[TokenNetwork]:
        for row in self.conn.execute("SELECT address FROM token_network"):
            yield TokenNetwork(token_network_address=decode_hex(row[0]))

    def prepare_feedback(self, token: FeedbackToken, route: List[Address]) -> None:
        hexed_route = [to_checksum_address(e) for e in route]
        token_dict = dict(
            token_id=token.id.hex,
            creation_time=token.creation_time,
            token_network_address=to_checksum_address(token.token_network_address),
            route=json.dumps(hexed_route),
        )
        self.insert("feedback", token_dict)

    def update_feedback(self, token: FeedbackToken, route: List[Address], successful: bool) -> int:
        hexed_route = [to_checksum_address(e) for e in route]
        token_dict = dict(
            token_id=token.id.hex,
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
                token_network_address=decode_hex(token["token_network_address"]),
                id=UUID(token["token_id"]),
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

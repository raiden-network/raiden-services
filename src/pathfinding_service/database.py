import os
from typing import Iterator, Optional

import structlog
from eth_utils import decode_hex, to_checksum_address

from pathfinding_service.model import IOU
from pathfinding_service.model.channel_view import ChannelView
from pathfinding_service.model.token_network import TokenNetwork
from raiden.utils.typing import Address, BlockNumber, ChannelID, TokenAmount
from raiden_libs.database import BaseDatabase, hex256

log = structlog.get_logger(__name__)


class PFSDatabase(BaseDatabase):
    """ Store data that needs to persist between PFS restarts """

    schema_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "schema.sql")

    def __init__(
        self,
        filename: str,
        chain_id: int,
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

    def upsert_iou(self, iou: IOU) -> None:
        iou_dict = IOU.Schema(strict=True).dump(iou)[0]
        for key in ("amount", "expiration_block"):
            iou_dict[key] = hex256(iou_dict[key])
        self.conn.execute(
            """
            INSERT OR REPLACE INTO iou (
                sender, amount, expiration_block, signature, claimed
            ) VALUES (
                :sender, :amount, :expiration_block, :signature, :claimed
            )
        """,
            iou_dict,
        )

    def get_latest_known_block(self) -> BlockNumber:
        return self.conn.execute("SELECT latest_known_block FROM blockchain").fetchone()[0]

    def update_lastest_known_block(self, latest_known_block: BlockNumber) -> None:
        self.conn.execute("UPDATE blockchain SET latest_known_block = ?", [latest_known_block])

    def get_ious(
        self,
        sender: Address = None,
        expiration_block: BlockNumber = None,
        claimed: bool = None,
        expires_before: BlockNumber = None,
        amount_at_least: TokenAmount = None,
    ) -> Iterator[IOU]:
        query = "SELECT * FROM iou WHERE 1=1"
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
            yield IOU.Schema(strict=True).load(iou_dict)[0]

    def get_iou(
        self, sender: Address, expiration_block: BlockNumber = None, claimed: bool = None
    ) -> Optional[IOU]:
        try:
            return next(self.get_ious(sender, expiration_block, claimed))
        except StopIteration:
            return None

    def upsert_channel_view(self, channel_view: ChannelView) -> None:
        cv_dict = ChannelView.Schema(strict=True, exclude=["state"]).dump(channel_view)[0]
        for key in (
            "channel_id",
            "settle_timeout",
            "capacity",
            "reveal_timeout",
            "deposit",
            "update_nonce",
            "absolute_fee",
        ):
            cv_dict[key] = hex256(cv_dict[key])
        self.conn.execute(
            """
            INSERT OR REPLACE INTO channel_view (
                token_network_address, channel_id, participant1, participant2,
                settle_timeout, capacity, reveal_timeout, deposit,
                update_nonce, absolute_fee, relative_fee
            ) VALUES (
                :token_network_address,
                :channel_id,
                :participant1, :participant2,
                :settle_timeout,
                :capacity,
                :reveal_timeout,
                :deposit,
                :update_nonce,
                :absolute_fee,
                :relative_fee
            )
        """,
            cv_dict,
        )

    def get_channel_views(self) -> Iterator[ChannelView]:
        query = "SELECT * FROM channel_view"
        for row in self.conn.execute(query):
            cv_dict = dict(zip(row.keys(), row))
            yield ChannelView.Schema().load(cv_dict)[0]

    def delete_channel_views(self, channel_id: ChannelID) -> None:
        self.conn.execute("DELETE FROM channel_view WHERE channel_id = ?", [channel_id])

    def get_token_networks(self) -> Iterator[TokenNetwork]:
        for row in self.conn.execute("SELECT address FROM token_network"):
            yield TokenNetwork(token_network_address=decode_hex(row[0]))

import os
from typing import Iterator, Optional

import structlog

from pathfinding_service.model import IOU
from pathfinding_service.model.channel_view import ChannelView
from pathfinding_service.model.token_network import TokenNetwork
from raiden.utils.typing import BlockNumber, ChannelID, TokenAmount
from raiden_libs.database import BaseDatabase, hex256
from raiden_libs.types import Address

log = structlog.get_logger(__name__)


class PFSDatabase(BaseDatabase):
    """ Store data that needs to persist between PFS restarts """

    schema_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'schema.sql')

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
        self.conn.execute(
            """
            INSERT OR REPLACE INTO iou (
                sender, amount, expiration_block, signature, claimed
            ) VALUES (
                :sender, printf('0x%064x', :amount), printf('0x%064x', :expiration_block),
                :signature, :claimed
            )
        """,
            iou_dict,
        )

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
            args.append(sender)
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
            iou_dict['receiver'] = self.pfs_address
            yield IOU.Schema().load(iou_dict)[0]

    def get_iou(
        self, sender: Address, expiration_block: BlockNumber = None, claimed: bool = None
    ) -> Optional[IOU]:
        try:
            return next(self.get_ious(sender, expiration_block, claimed))
        except StopIteration:
            return None

    def upsert_channel_view(self, channel_view: ChannelView) -> None:
        cv_dict = ChannelView.Schema(strict=True, exclude=['state']).dump(channel_view)[0]
        self.conn.execute(
            """
            INSERT OR REPLACE INTO channel_view (
                token_network_address, channel_id, participant1, participant2,
                settle_timeout, capacity, reveal_timeout, deposit,
                update_nonce, absolute_fee, relative_fee
            ) VALUES (
                :token_network_address,
                printf('0x%064x', :channel_id),
                :participant1, :participant2,
                printf('0x%064x', :settle_timeout),
                printf('0x%064x', :capacity),
                printf('0x%064x', :reveal_timeout),
                printf('0x%064x', :deposit),
                printf('0x%064x', :update_nonce),
                :absolute_fee, :relative_fee
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
            yield TokenNetwork(token_network_address=row[0])

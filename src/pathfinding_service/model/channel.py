from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import ClassVar, Tuple, Type

import marshmallow
from eth_utils import to_checksum_address
from marshmallow.fields import NaiveDateTime
from marshmallow_dataclass import add_schema

from pathfinding_service.constants import DEFAULT_REVEAL_TIMEOUT
from pathfinding_service.exceptions import InvalidFeeUpdate
from raiden.transfer.mediated_transfer.mediation_fee import FeeScheduleState as FeeScheduleRaiden
from raiden.utils.typing import (
    Address,
    BlockTimeout,
    ChannelID,
    Nonce,
    Optional,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_libs.marshmallow import ChecksumAddress


@dataclass
class FeeSchedule(FeeScheduleRaiden):
    timestamp: datetime = field(
        metadata={"marshmallow_field": NaiveDateTime()}, default=datetime(2000, 1, 1)
    )

    @classmethod
    def from_raiden(cls, fee_schedule: FeeScheduleRaiden, timestamp: datetime) -> "FeeSchedule":
        kwargs = asdict(fee_schedule)
        kwargs.pop("_penalty_func")
        return FeeSchedule(timestamp=timestamp, **kwargs)


@add_schema
@dataclass
class Channel:
    # pylint: disable=too-many-instance-attributes
    token_network_address: TokenNetworkAddress = field(
        metadata={"marshmallow_field": ChecksumAddress(required=True)}
    )
    channel_id: ChannelID
    participant1: Address = field(metadata={"marshmallow_field": ChecksumAddress(required=True)})
    participant2: Address = field(metadata={"marshmallow_field": ChecksumAddress(required=True)})
    settle_timeout: BlockTimeout
    fee_schedule1: FeeSchedule = field(default_factory=FeeSchedule)
    fee_schedule2: FeeSchedule = field(default_factory=FeeSchedule)

    # Set by PFSCapacityUpdate
    capacity1: TokenAmount = TokenAmount(0)
    capacity2: TokenAmount = TokenAmount(0)
    update_nonce1: Nonce = Nonce(0)
    update_nonce2: Nonce = Nonce(0)
    reveal_timeout1: BlockTimeout = DEFAULT_REVEAL_TIMEOUT
    reveal_timeout2: BlockTimeout = DEFAULT_REVEAL_TIMEOUT

    Schema: ClassVar[Type[marshmallow.Schema]]

    @property
    def views(self) -> Tuple["ChannelView", "ChannelView"]:
        return ChannelView(channel=self), ChannelView(channel=self, reverse=True)


@dataclass
class ChannelView:
    """
    Unidirectional view of a bidirectional channel

    No data is stored inside the ChannelView.
    """

    channel: Channel
    reverse: bool = False

    @property
    def channel_id(self) -> ChannelID:
        return self.channel.channel_id

    @property
    def participant1(self) -> Address:
        return self.channel.participant2 if self.reverse else self.channel.participant1

    @property
    def participant2(self) -> Address:
        return self.channel.participant1 if self.reverse else self.channel.participant2

    @property
    def settle_timeout(self) -> int:
        return self.channel.settle_timeout

    @property
    def token_network_address(self) -> TokenNetworkAddress:
        return self.channel.token_network_address

    @property
    def capacity(self) -> TokenAmount:
        return self.channel.capacity2 if self.reverse else self.channel.capacity1

    @capacity.setter
    def capacity(self, value: TokenAmount) -> None:
        if self.reverse:
            self.channel.capacity2 = value
        else:
            self.channel.capacity1 = value

    @property
    def capacity_partner(self) -> TokenAmount:
        return self.channel.capacity1 if self.reverse else self.channel.capacity2

    @property
    def reveal_timeout(self) -> int:
        return self.channel.reveal_timeout2 if self.reverse else self.channel.reveal_timeout1

    @reveal_timeout.setter
    def reveal_timeout(self, value: BlockTimeout) -> None:
        if self.reverse:
            self.channel.reveal_timeout2 = value
        else:
            self.channel.reveal_timeout1 = value

    @property
    def update_nonce(self) -> Nonce:
        return self.channel.update_nonce2 if self.reverse else self.channel.update_nonce1

    @update_nonce.setter
    def update_nonce(self, value: Nonce) -> None:
        if self.reverse:
            self.channel.update_nonce2 = value
        else:
            self.channel.update_nonce1 = value

    @property
    def fee_schedule_sender(self) -> FeeSchedule:
        return self.channel.fee_schedule2 if self.reverse else self.channel.fee_schedule1

    @property
    def fee_schedule_receiver(self) -> FeeSchedule:
        return self.channel.fee_schedule1 if self.reverse else self.channel.fee_schedule2

    def update_capacity(
        self,
        capacity: TokenAmount,
        nonce: Nonce = Nonce(0),
        reveal_timeout: Optional[BlockTimeout] = None,
    ) -> None:
        self.update_nonce = nonce
        self.capacity = capacity
        if reveal_timeout is not None:
            self.reveal_timeout = reveal_timeout

    def set_fee_schedule(self, fee_schedule: FeeSchedule) -> None:
        if self.fee_schedule_sender.timestamp >= fee_schedule.timestamp:
            raise InvalidFeeUpdate("Timestamp must increase between fee updates")
        if self.reverse:
            self.channel.fee_schedule2 = fee_schedule
        else:
            self.channel.fee_schedule1 = fee_schedule

    def __repr__(self) -> str:
        return "<ChannelView cid={} from={} to={} capacity={}>".format(
            self.channel_id,
            to_checksum_address(self.participant1),
            to_checksum_address(self.participant2),
            self.capacity,
        )

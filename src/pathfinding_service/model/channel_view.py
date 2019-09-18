from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import ClassVar, Type

import marshmallow
from eth_utils import to_checksum_address
from marshmallow_dataclass import add_schema

from pathfinding_service.constants import DEFAULT_REVEAL_TIMEOUT
from pathfinding_service.exceptions import InvalidPFSFeeUpdate
from raiden.exceptions import UndefinedMediationFee
from raiden.transfer.mediated_transfer.mediation_fee import FeeScheduleState as FeeScheduleRaiden
from raiden.utils.typing import (
    Address,
    Balance,
    ChannelID,
    FeeAmount,
    Nonce,
    Optional,
    PaymentWithFeeAmount,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_libs.marshmallow import ChecksumAddress


@dataclass
class FeeSchedule(FeeScheduleRaiden):
    timestamp: datetime = datetime(2000, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def from_raiden(cls, fee_schedule: FeeScheduleRaiden, timestamp: datetime) -> "FeeSchedule":
        kwargs = asdict(fee_schedule)
        kwargs.pop("_penalty_func")
        return FeeSchedule(timestamp=timestamp, **kwargs)


@add_schema
@dataclass
class ChannelView:
    """
    Unidirectional view of a bidirectional channel.
    """

    channel_id: ChannelID
    participant1: Address = field(metadata={"marshmallow_field": ChecksumAddress(required=True)})
    participant2: Address = field(metadata={"marshmallow_field": ChecksumAddress(required=True)})
    settle_timeout: int
    token_network_address: TokenNetworkAddress = field(
        metadata={"marshmallow_field": ChecksumAddress(required=True)}
    )
    capacity: TokenAmount = TokenAmount(0)
    reveal_timeout: int = DEFAULT_REVEAL_TIMEOUT
    update_nonce: Nonce = Nonce(0)
    fee_schedule_sender: FeeSchedule = field(default_factory=FeeSchedule)
    fee_schedule_receiver: FeeSchedule = field(default_factory=FeeSchedule)
    Schema: ClassVar[Type[marshmallow.Schema]]

    def update_capacity(
        self, capacity: TokenAmount, nonce: Nonce = Nonce(0), reveal_timeout: int = None
    ) -> None:
        self.update_nonce = nonce
        self.capacity = capacity
        if reveal_timeout is not None:
            self.reveal_timeout = reveal_timeout

    def backwards_fee_sender(
        self, balance: Balance, amount: PaymentWithFeeAmount
    ) -> Optional[FeeAmount]:
        """Returns the mediation fee for this channel when transferring the given amount"""
        try:
            imbalance_fee = self.fee_schedule_sender.imbalance_fee(amount=amount, balance=balance)
        except UndefinedMediationFee:
            return None

        flat_fee = self.fee_schedule_sender.flat
        prop_fee = int(round(amount * self.fee_schedule_sender.proportional / 1e6))
        return FeeAmount(flat_fee + prop_fee + imbalance_fee)

    def backwards_fee_receiver(
        self, balance: Balance, amount: PaymentWithFeeAmount
    ) -> Optional[FeeAmount]:
        """Returns the mediation fee for this channel when receiving the given amount"""

        def fee_in(imbalance_fee: FeeAmount) -> FeeAmount:
            return FeeAmount(
                round(
                    (
                        (amount + self.fee_schedule_receiver.flat + imbalance_fee)
                        / (1 - self.fee_schedule_receiver.proportional / 1e6)
                    )
                    - amount
                )
            )

        try:
            imbalance_fee = self.fee_schedule_receiver.imbalance_fee(
                amount=PaymentWithFeeAmount(-(amount - fee_in(imbalance_fee=FeeAmount(0)))),
                balance=balance,
            )
        except UndefinedMediationFee:
            return None

        return fee_in(imbalance_fee=imbalance_fee)

    def set_sender_fee_schedule(self, fee_schedule: FeeSchedule) -> None:
        if self.fee_schedule_sender.timestamp >= fee_schedule.timestamp:
            raise InvalidPFSFeeUpdate("Timestamp must increase between fee updates")
        self.fee_schedule_sender = fee_schedule

    def set_receiver_fee_schedule(self, fee_schedule: FeeSchedule) -> None:
        if self.fee_schedule_receiver.timestamp >= fee_schedule.timestamp:
            raise InvalidPFSFeeUpdate("Timestamp must increase between fee updates")
        self.fee_schedule_receiver = fee_schedule

    def __repr__(self) -> str:
        return "<ChannelView cid={} from={} to={} capacity={}>".format(
            self.channel_id,
            to_checksum_address(self.participant1),
            to_checksum_address(self.participant2),
            self.capacity,
        )

from dataclasses import dataclass, field
from typing import ClassVar, List, Optional, Type

import marshmallow
from marshmallow_dataclass import add_schema

from pathfinding_service.config import DEFAULT_REVEAL_TIMEOUT
from raiden.utils.typing import (
    Address,
    ChannelID,
    FeeAmount,
    Nonce,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_libs.marshmallow import ChecksumAddress


@dataclass
class FeeSchedule:
    flat: FeeAmount
    proportional: float
    imbalance_penalty: Optional[List[List[FeeAmount]]] = None

    def reversed(self) -> "FeeSchedule":
        # pylint: disable=not-an-iterable
        if not self.imbalance_penalty:
            return self
        max_x = max(x for x, penalty in self.imbalance_penalty)
        return FeeSchedule(
            flat=self.flat,
            proportional=self.proportional,
            imbalance_penalty=[
                [FeeAmount(max_x - x), penalty] for x, penalty in self.imbalance_penalty
            ],
        )


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
    capacity: TokenAmount = None  # type: ignore
    reveal_timeout: int = DEFAULT_REVEAL_TIMEOUT
    deposit: TokenAmount = TokenAmount(0)
    update_nonce: Nonce = Nonce(0)
    fee_schedule: FeeSchedule = field(
        default_factory=lambda: FeeSchedule(flat=FeeAmount(0), proportional=FeeAmount(0))
    )
    Schema: ClassVar[Type[marshmallow.Schema]]

    def __post_init__(self) -> None:
        if self.capacity is None:
            self.capacity = self.deposit

    def update_deposit(self, total_deposit: TokenAmount) -> None:
        if total_deposit > self.deposit:
            self.capacity = TokenAmount(self.capacity + total_deposit - self.deposit)
            self.deposit = TokenAmount(total_deposit)

    def update_capacity(
        self, capacity: TokenAmount, nonce: Nonce = Nonce(0), reveal_timeout: int = None
    ) -> None:
        self.update_nonce = nonce
        self.capacity = capacity
        if reveal_timeout is not None:
            self.reveal_timeout = reveal_timeout

    def fee(self, amount: TokenAmount) -> int:
        """Return the mediation fee for this channel when transferring the given amount"""
        return int(self.fee_schedule.flat + amount * self.fee_schedule.proportional)

    def __repr__(self) -> str:
        return "<ChannelView from={} to={} capacity={}>".format(
            self.participant1, self.participant2, self.capacity
        )

from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Callable, ClassVar, List, Optional, Sequence, Type

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


class Interpolate:  # pylint: disable=too-few-public-methods
    def __init__(self, x_list: Sequence, y_list: Sequence):
        if any(y - x <= 0 for x, y in zip(x_list, x_list[1:])):
            raise ValueError("x_list must be in strictly ascending order!")
        self.x_list = x_list
        self.y_list = y_list
        intervals = zip(x_list, x_list[1:], y_list, y_list[1:])
        self.slopes = [(y2 - y1) / (x2 - x1) for x1, x2, y1, y2 in intervals]

    def __call__(self, x: float) -> float:
        assert self.x_list[0] <= x <= self.x_list[-1]
        if x == self.x_list[-1]:
            return self.y_list[-1]
        i = bisect_right(self.x_list, x) - 1
        return self.y_list[i] + self.slopes[i] * (x - self.x_list[i])


@dataclass
class FeeSchedule:
    # pylint: disable=not-an-iterable
    flat: FeeAmount = FeeAmount(0)
    proportional: float = FeeAmount(0)
    imbalance_penalty: Optional[List[List[TokenAmount]]] = None
    _penalty_func: Callable = field(init=False)

    def __post_init__(self) -> None:
        if self.imbalance_penalty:
            assert isinstance(self.imbalance_penalty, list)
            x_list, y_list = tuple(zip(*self.imbalance_penalty))
            # see https://github.com/python/mypy/issues/2427 for type problem
            self._penalty_func = Interpolate(x_list, y_list)  # type: ignore
        else:
            self._penalty_func = lambda amount: 0  # type: ignore

    def fee(self, amount: TokenAmount, capacity: TokenAmount) -> FeeAmount:
        imbalance_fee = self._penalty_func(capacity + amount) - self._penalty_func(capacity)
        return FeeAmount(round(self.flat + amount * self.proportional + imbalance_fee))

    def reversed(self) -> "FeeSchedule":
        if not self.imbalance_penalty:
            return self
        max_x = max(x for x, penalty in self.imbalance_penalty)
        return FeeSchedule(
            flat=self.flat,
            proportional=self.proportional,
            imbalance_penalty=[
                [TokenAmount(max_x - x), penalty] for x, penalty in self.imbalance_penalty
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
    fee_schedule: FeeSchedule = field(default_factory=FeeSchedule)
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

    def fee_out(self, amount: TokenAmount) -> int:
        """Return the mediation fee for this channel when transferring the given amount"""
        return int(self.fee_schedule.flat + amount * self.fee_schedule.proportional)

    def fee_in(self, amount: TokenAmount) -> int:
        """Return the mediation fee for this channel when receiving the given amount"""
        return int(self.fee_schedule.flat + amount * self.fee_schedule.proportional)

    def __repr__(self) -> str:
        return "<ChannelView from={} to={} capacity={}>".format(
            self.participant1, self.participant2, self.capacity
        )

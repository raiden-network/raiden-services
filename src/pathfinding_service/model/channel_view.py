from dataclasses import dataclass, field
from typing import ClassVar, Type

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
    absolute_fee: FeeAmount = FeeAmount(0)
    relative_fee: float = 0
    Schema: ClassVar[Type[marshmallow.Schema]]

    def __post_init__(self) -> None:
        if self.capacity is None:
            self.capacity = self.deposit

    # TODO: define another function update_deposit
    def update_capacity(
        self,
        nonce: Nonce = Nonce(0),
        capacity: TokenAmount = TokenAmount(0),
        reveal_timeout: int = None,
        deposit: TokenAmount = None,
        mediation_fee: FeeAmount = FeeAmount(0),
    ) -> None:
        self.update_nonce = nonce
        self.capacity = capacity
        if reveal_timeout is not None:
            self.reveal_timeout = reveal_timeout
        # FIXME: think about edge cases
        if deposit is not None:
            self.deposit = deposit
            if self.capacity is not None:
                self.capacity = TokenAmount(self.capacity + deposit)

        self.absolute_fee = mediation_fee

    def fee(self, amount: TokenAmount) -> int:
        """Return the mediation fee for this channel when transferring the given amount"""
        return int(self.absolute_fee + amount * self.relative_fee)

    def __repr__(self) -> str:
        return "<ChannelView from={} to={} capacity={}>".format(
            self.participant1, self.participant2, self.capacity
        )

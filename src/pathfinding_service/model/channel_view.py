from dataclasses import dataclass, field
from enum import Enum

from eth_utils import is_checksum_address

from pathfinding_service.config import DEFAULT_REVEAL_TIMEOUT
from raiden.utils.typing import ChannelID, FeeAmount, Nonce, TokenAmount
from raiden_libs.types import Address


@dataclass
class ChannelView:
    """
    Unidirectional view of a bidirectional channel.
    """

    class State(Enum):
        OPEN = 1
        SETTLING = 2
        SETTLED = 3

    channel_id: ChannelID
    participant1: Address
    participant2: Address
    settle_timeout: int
    capacity: int = field(init=False)
    reveal_timeout: int = DEFAULT_REVEAL_TIMEOUT
    deposit: TokenAmount = TokenAmount(0)
    state: State = State.OPEN
    update_nonce: int = field(default=0, init=False)
    absolute_fee = FeeAmount(0)
    relative_fee: float = 0

    def __post_init__(self) -> None:
        assert is_checksum_address(self.participant1)
        assert is_checksum_address(self.participant2)
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
        return '<ChannelView from={} to={} capacity={}>'.format(
            self.participant1, self.participant2, self.capacity
        )

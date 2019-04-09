from enum import Enum

from eth_utils import is_checksum_address

from pathfinding_service.config import DEFAULT_REVEAL_TIMEOUT
from raiden.utils.typing import ChannelID, FeeAmount, Nonce, TokenAmount
from raiden_libs.types import Address


class ChannelView:
    """
    Unidirectional view of a bidirectional channel.
    """

    class State(Enum):
        OPEN = 1
        SETTLING = 2
        SETTLED = 3

    def __init__(
        self,
        channel_id: ChannelID,
        participant1: Address,
        participant2: Address,
        settle_timeout: int,
        deposit: TokenAmount = TokenAmount(0),
        reveal_timeout: int = DEFAULT_REVEAL_TIMEOUT,
    ):
        assert is_checksum_address(participant1)
        assert is_checksum_address(participant2)

        self.self = participant1
        self.partner = participant2

        self._deposit = deposit
        self._capacity = deposit
        self.mediation_fee = FeeAmount(0)
        self.state = ChannelView.State.OPEN
        self.channel_id = channel_id
        self.settle_timeout = settle_timeout
        self.reveal_timeout = reveal_timeout
        self.update_nonce = 0
        self.absolute_fee = 0
        self.relative_fee: float = 0

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
        self._capacity = capacity
        if reveal_timeout is not None:
            self.reveal_timeout = reveal_timeout
        # FIXME: think about edge cases
        if deposit is not None:
            self._deposit = deposit
            if self._capacity is not None:
                self._capacity = TokenAmount(self._capacity + deposit)

        self.mediation_fee = mediation_fee

    @property
    def deposit(self) -> TokenAmount:
        return self._deposit

    @property
    def capacity(self) -> TokenAmount:
        return self._capacity

    def fee(self, amount: TokenAmount) -> int:
        """Return the mediation fee for this channel when transferring the given amount"""
        return int(self.absolute_fee + amount * self.relative_fee)

    def __repr__(self) -> str:
        return '<ChannelView from={} to={} capacity={}>'.format(
            self.self, self.partner, self.capacity
        )

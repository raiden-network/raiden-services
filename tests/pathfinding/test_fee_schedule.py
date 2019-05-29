from typing import Dict, List

import pytest
from eth_utils import decode_hex

from pathfinding_service.model.channel_view import FeeSchedule, Interpolate
from pathfinding_service.model.token_network import FeeUpdate, TokenNetwork
from raiden.network.transport.matrix.utils import AddressReachability
from raiden.transfer.identifiers import CanonicalIdentifier
from raiden.utils.typing import (
    Address,
    ChainID,
    ChannelID,
    FeeAmount as FA,
    TokenAmount as TA,
    TokenNetworkAddress,
)


def test_basic_fee():
    flat_schedule = FeeSchedule(flat=FA(2))
    assert flat_schedule.fee(TA(10), capacity=TA(0)) == FA(2)

    prop_schedule = FeeSchedule(proportional=0.01)
    assert prop_schedule.fee(TA(40), capacity=TA(0)) == FA(0)
    assert prop_schedule.fee(TA(60), capacity=TA(0)) == FA(1)
    assert prop_schedule.fee(TA(1000), capacity=TA(0)) == FA(10)

    combined_schedule = FeeSchedule(flat=FA(2), proportional=0.01)
    assert combined_schedule.fee(TA(60), capacity=TA(0)) == FA(3)


def test_imbalance_penalty():
    v_schedule = FeeSchedule(
        imbalance_penalty=[(TA(0), FA(10)), (TA(50), FA(0)), (TA(100), FA(10))]
    )
    assert v_schedule.fee(capacity=TA(100 - 0), amount=TA(50)) == FA(-10)
    assert v_schedule.fee(capacity=TA(100 - 50), amount=TA(50)) == FA(10)
    assert v_schedule.fee(capacity=TA(100 - 0), amount=TA(10)) == FA(-2)
    assert v_schedule.fee(capacity=TA(100 - 10), amount=TA(10)) == FA(-2)
    assert v_schedule.fee(capacity=TA(100 - 0), amount=TA(20)) == FA(-4)
    assert v_schedule.fee(capacity=TA(100 - 40), amount=TA(20)) == FA(0)


class PrettyBytes(bytes):
    def __repr__(self):
        return "a%x" % int.from_bytes(self, byteorder="big")


def a(int_addr) -> Address:  # pylint: disable=invalid-name
    """Create an address from an int with a short representation.

    This is helpful in tests because
    * Address creation is concise
    * You can easily match `a(1)` in your test with `a1` in your test output
    """
    return Address(PrettyBytes([0] * 19 + [int_addr]))


class TestTokenNetwork(TokenNetwork):
    def __init__(self, channels: List[dict]):
        super().__init__(token_network_address=TokenNetworkAddress(a(255)))

        # open channels
        for chan in channels:
            self.handle_channel_opened_event(
                channel_identifier=ChannelID(100),
                participant1=a(chan["participant1"]),
                participant2=a(chan["participant2"]),
                settle_timeout=100,
            )

        # set default capacity
        for _, _, cv in self.G.edges(data="view"):
            cv.capacity = 100

        # create reachability mapping for testing
        self.address_to_reachability: Dict[Address, AddressReachability] = {
            node: AddressReachability.REACHABLE for node in self.G.nodes
        }

    def set_fee(self, node1: int, node2: int, fee_schedule: FeeSchedule):
        channel_id = self.G[a(node1)][a(node2)]["view"].channel_id
        self.handle_channel_fee_update(
            FeeUpdate(
                CanonicalIdentifier(
                    chain_identifier=ChainID(1),
                    token_network_address=self.address,
                    channel_identifier=channel_id,
                ),
                a(node1),
                a(node2),
                fee_schedule,
            )
        )

    def estimate_fee(self, initator: int, target: int, value=TA(10), max_paths=1):
        result = self.get_paths(
            source=a(initator),
            target=a(target),
            value=value,
            max_paths=max_paths,
            address_to_reachability=self.address_to_reachability,
        )
        if not result:
            return None
        return result[0]["estimated_fee"]


def test_fees_in_routing():
    tn = TestTokenNetwork(
        channels=[dict(participant1=1, participant2=2), dict(participant1=2, participant2=3)]
    )

    # Make sure that routing works and the default fees are zero
    result = tn.get_paths(
        source=a(1),
        target=a(3),
        value=TA(10),
        max_paths=1,
        address_to_reachability=tn.address_to_reachability,
    )
    assert len(result) == 1
    assert [PrettyBytes(decode_hex(node)) for node in result[0]["path"]] == [a(1), a(2), a(3)]
    assert result[0]["estimated_fee"] == 0

    # Fees for the initiator are ignored
    tn.set_fee(1, 2, FeeSchedule(flat=FA(1)))
    assert tn.estimate_fee(1, 3) == 0

    # Node 2 demands fees for incoming transfers
    tn.set_fee(2, 1, FeeSchedule(flat=FA(1)))
    assert tn.estimate_fee(1, 3) == 1

    # Node 2 demands fees for outgoing transfers
    tn.set_fee(2, 3, FeeSchedule(flat=FA(1)))
    assert tn.estimate_fee(1, 3) == 2

    # Same fee in the opposite direction
    assert tn.estimate_fee(3, 1) == 2

    # Reset fees to zero
    tn.set_fee(1, 2, FeeSchedule())
    tn.set_fee(2, 1, FeeSchedule())
    tn.set_fee(2, 3, FeeSchedule())

    # Now let's try imbalance fees
    tn.set_fee(2, 3, FeeSchedule(imbalance_penalty=[(TA(0), FA(0)), (TA(200), FA(200))]))
    assert tn.estimate_fee(1, 3) == 10
    assert tn.estimate_fee(3, 1) == -10

    # When the range covered by the imbalance_penalty does include the
    # necessary balance values, the route should be considered invalid.
    tn.set_fee(2, 3, FeeSchedule(imbalance_penalty=[(TA(0), FA(0)), (TA(80), FA(200))]))
    assert tn.estimate_fee(1, 3) is None


def test_compounding_fees():
    """ The transferred amount needs to include the fees for all mediators.
    Earlier mediators will apply the proportional fee not only on the payment
    amount, but also on the fees for later mediators.
    """
    tn = TestTokenNetwork(
        channels=[
            dict(participant1=1, participant2=2),
            dict(participant1=2, participant2=3),
            dict(participant1=3, participant2=4),
        ]
    )
    tn.set_fee(2, 3, FeeSchedule(proportional=1))  # this is a 100% fee
    tn.set_fee(3, 4, FeeSchedule(proportional=1))
    assert tn.estimate_fee(1, 4, value=TA(1)) == (
        1  # fee for node 3
        + 2  # fee for node 2, which mediates 1 token for the payment and 1 for node 3's fees
    )


def test_interpolation():
    interp = Interpolate((0, 100), (0, 100))
    for i in range(101):
        assert interp(i) == i

    interp = Interpolate((0, 50, 100), (0, 100, 200))
    for i in range(101):
        assert interp(i) == 2 * i

    interp = Interpolate((0, 50, 100), (0, -50, 50))
    assert interp(40) == -40
    assert interp(60) == -30
    assert interp(90) == 30
    assert interp(99) == 48

    interp = Interpolate((0, 100), (12.35, 67.2))
    assert interp(0) == 12.35
    assert interp(50) == pytest.approx((12.35 + 67.2) / 2)
    assert interp(100) == 67.2

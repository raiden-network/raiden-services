import itertools
from datetime import datetime, timezone
from typing import Dict, List

from eth_utils import decode_hex

from pathfinding_service.model.token_network import TokenNetwork
from raiden.constants import EMPTY_SIGNATURE
from raiden.messages import FeeScheduleState as RaidenFeeSchedule, FeeUpdate
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


class TokenNetworkForTests(TokenNetwork):
    def __init__(self, channels: List[dict]):
        super().__init__(token_network_address=TokenNetworkAddress(a(255)))

        # open channels
        channel_ids = itertools.count(100)
        for chan in channels:
            self.handle_channel_opened_event(
                channel_identifier=ChannelID(next(channel_ids)),
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

    def set_fee(self, node1: int, node2: int, **fee_params):
        channel_id = self.G[a(node1)][a(node2)]["view"].channel_id
        self.handle_channel_fee_update(
            FeeUpdate(
                canonical_identifier=CanonicalIdentifier(
                    chain_identifier=ChainID(1),
                    token_network_address=self.address,
                    channel_identifier=channel_id,
                ),
                updating_participant=a(node1),
                fee_schedule=RaidenFeeSchedule(**fee_params),
                signature=EMPTY_SIGNATURE,
                timestamp=datetime.now(timezone.utc),
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
    tn = TokenNetworkForTests(
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
    tn.set_fee(1, 2, flat=FA(1))
    assert tn.estimate_fee(1, 3) == 0

    # Node 2 demands fees for incoming transfers
    tn.set_fee(2, 1, flat=FA(1))
    assert tn.estimate_fee(1, 3) == 1

    # Node 2 demands fees for outgoing transfers
    tn.set_fee(2, 3, flat=FA(1))
    assert tn.estimate_fee(1, 3) == 2

    # Same fee in the opposite direction
    assert tn.estimate_fee(3, 1) == 2

    # Reset fees to zero
    tn.set_fee(1, 2)
    tn.set_fee(2, 1)
    tn.set_fee(2, 3)

    # Now let's try imbalance fees
    tn.set_fee(2, 3, imbalance_penalty=[(TA(0), FA(0)), (TA(200), FA(200))])
    assert tn.estimate_fee(1, 3) == 10
    assert tn.estimate_fee(3, 1) == -10

    # When the range covered by the imbalance_penalty does include the
    # necessary balance values, the route should be considered invalid.
    tn.set_fee(2, 3, imbalance_penalty=[(TA(0), FA(0)), (TA(80), FA(200))])
    assert tn.estimate_fee(1, 3) is None


def test_compounding_fees():
    """ The transferred amount needs to include the fees for all mediators.
    Earlier mediators will apply the proportional fee not only on the payment
    amount, but also on the fees for later mediators.
    """
    tn = TokenNetworkForTests(
        channels=[
            dict(participant1=1, participant2=2),
            dict(participant1=2, participant2=3),
            dict(participant1=3, participant2=4),
        ]
    )
    tn.set_fee(2, 3, proportional=1e6)  # this is a 100% fee
    tn.set_fee(3, 4, proportional=1e6)
    assert tn.estimate_fee(1, 4, value=TA(1)) == (
        1  # fee for node 3
        + 2  # fee for node 2, which mediates 1 token for the payment and 1 for node 3's fees
    )

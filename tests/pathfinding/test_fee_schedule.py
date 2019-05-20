from eth_utils import decode_hex

from pathfinding_service.model.channel_view import FeeSchedule
from pathfinding_service.model.token_network import FeeUpdate, TokenNetwork
from raiden.network.transport.matrix.utils import AddressReachability
from raiden.transfer.identifiers import CanonicalIdentifier
from raiden.utils.typing import ChainID, FeeAmount as FA, TokenAmount as TA


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
        imbalance_penalty=[[TA(0), TA(10)], [TA(50), TA(0)], [TA(100), TA(10)]]
    )
    assert v_schedule.fee(capacity=TA(100 - 0), amount=TA(50)) == FA(-10)
    assert v_schedule.fee(capacity=TA(100 - 50), amount=TA(50)) == FA(10)
    assert v_schedule.fee(capacity=TA(100 - 0), amount=TA(10)) == FA(-2)
    assert v_schedule.fee(capacity=TA(100 - 10), amount=TA(10)) == FA(-2)
    assert v_schedule.fee(capacity=TA(100 - 0), amount=TA(20)) == FA(-4)
    assert v_schedule.fee(capacity=TA(100 - 40), amount=TA(20)) == FA(0)


class PrettyBytes(bytes):
    def __repr__(self):
        return "b%x" % int.from_bytes(self, byteorder="big")


def a(int_addr):  # pylint: disable=invalid-name
    return PrettyBytes([0] * 19 + [int_addr])


def test_fees_in_routing():
    network = TokenNetwork(token_network_address=a(255))
    network.address_to_reachability = {
        a(1): AddressReachability.REACHABLE,
        a(2): AddressReachability.REACHABLE,
        a(3): AddressReachability.REACHABLE,
    }
    network.handle_channel_opened_event(
        channel_identifier=a(100), participant1=a(1), participant2=a(2), settle_timeout=100
    )
    network.handle_channel_opened_event(
        channel_identifier=a(101), participant1=a(2), participant2=a(3), settle_timeout=100
    )
    for _, _, cv in network.G.edges(data="view"):
        cv.capacity = 100

    # Make sure that routing works and the default fees are zero
    result = network.get_paths(a(1), a(3), value=TA(10), max_paths=1)
    assert len(result) == 1
    assert [PrettyBytes(decode_hex(node)) for node in result[0]["path"]] == [a(1), a(2), a(3)]
    assert result[0]["estimated_fee"] == 0

    def set_fee(node1, node2, fee_schedule: FeeSchedule):
        channel_id = network.G[node1][node2]["view"].channel_id
        network.handle_channel_fee_update(
            FeeUpdate(
                CanonicalIdentifier(
                    chain_identifier=ChainID(1),
                    token_network_address=network.address,
                    channel_identifier=channel_id,
                ),
                node1,
                node2,
                fee_schedule,
            )
        )

    def estimate_fee(initator, target, value=TA(10), max_paths=1):
        result = network.get_paths(initator, target, value=value, max_paths=max_paths)
        return result[0]["estimated_fee"]

    # Fees for the initiator are ignored
    set_fee(a(1), a(2), FeeSchedule(flat=FA(1)))
    assert estimate_fee(a(1), a(3)) == 0

    # Node 2 demands fees for incoming transfers
    set_fee(a(2), a(1), FeeSchedule(flat=FA(1)))
    assert estimate_fee(a(1), a(3)) == 1

    # Node 2 demands fees for outgoing transfers
    set_fee(a(2), a(3), FeeSchedule(flat=FA(1)))
    assert estimate_fee(a(1), a(3)) == 2

    # Same fee in the opposite direction
    assert estimate_fee(a(3), a(1)) == 2

    # Reset fees to zero
    set_fee(a(1), a(2), FeeSchedule())
    set_fee(a(2), a(1), FeeSchedule())
    set_fee(a(2), a(3), FeeSchedule())

    # Now let's try imbalance fees
    set_fee(a(2), a(3), FeeSchedule(imbalance_penalty=[[TA(0), TA(0)], [TA(200), TA(200)]]))
    assert estimate_fee(a(1), a(3)) == 10
    assert estimate_fee(a(3), a(1)) == -10

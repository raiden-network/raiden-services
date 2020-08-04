import random
import time
from copy import deepcopy
from datetime import timedelta
from typing import List

import pytest
from eth_utils import to_canonical_address, to_checksum_address
from tests.pathfinding.utils import SimpleReachabilityContainer

from pathfinding_service.constants import DIVERSITY_PEN_DEFAULT
from pathfinding_service.model import ChannelView, TokenNetwork
from pathfinding_service.model.channel import Channel
from raiden.network.transport.matrix import AddressReachability
from raiden.utils.typing import (
    Address,
    BlockTimeout,
    ChannelID,
    FeeAmount,
    PaymentAmount,
    ProportionalFeeAmount,
    TokenAmount,
    TokenNetworkAddress,
)


def test_edge_weight(addresses):
    # pylint: disable=assigning-non-slot
    channel_id = ChannelID(1)
    participant1 = addresses[0]
    participant2 = addresses[1]
    capacity = TokenAmount(int(20 * 1e18))
    capacity_partner = TokenAmount(int(10 * 1e18))
    settle_timeout = BlockTimeout(15)
    channel = Channel(
        token_network_address=TokenNetworkAddress(bytes([1])),
        channel_id=channel_id,
        participant1=participant1,
        participant2=participant2,
        capacity1=capacity,
        capacity2=capacity_partner,
        settle_timeout=settle_timeout,
    )
    view, view_partner = channel.views
    amount = PaymentAmount(int(1e18))  # one RDN

    # no penalty
    assert (
        TokenNetwork.edge_weight(
            visited=dict(), view=view, view_from_partner=view_partner, amount=amount, fee_penalty=0
        )
        == 1
    )

    # channel already used in a previous route
    assert (
        TokenNetwork.edge_weight(
            visited={channel_id: 2},
            view=view,
            view_from_partner=view_partner,
            amount=amount,
            fee_penalty=0,
        )
        == 3
    )

    # absolute fee
    view.fee_schedule_sender.flat = FeeAmount(int(0.03e18))
    assert (
        TokenNetwork.edge_weight(
            visited=dict(),
            view=view,
            view_from_partner=view_partner,
            amount=amount,
            fee_penalty=100,
        )
        == 4
    )

    # relative fee
    view.fee_schedule_sender.flat = FeeAmount(0)
    view.fee_schedule_sender.proportional = ProportionalFeeAmount(int(0.01e6))
    assert (
        TokenNetwork.edge_weight(
            visited=dict(),
            view=view,
            view_from_partner=view_partner,
            amount=amount,
            fee_penalty=100,
        )
        == 2
    )

    # partner has not enough capacity for refund (no_refund_weight) -> edge weight +1
    view_partner.capacity = TokenAmount(0)
    assert (
        TokenNetwork.edge_weight(
            visited=dict(),
            view=view,
            view_from_partner=view_partner,
            amount=amount,
            fee_penalty=100,
        )
        == 3
    )


@pytest.mark.usefixtures("populate_token_network_case_1")
def test_routing_simple(
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
):
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    view01: ChannelView = token_network_model.G[addresses[0]][addresses[1]]["view"]
    view10: ChannelView = token_network_model.G[addresses[1]][addresses[0]]["view"]

    assert view01.fee_schedule_sender.flat == 0
    assert view01.capacity == 90
    assert view10.capacity == 60

    # 0->2->3 is the shortest path, but has no capacity, so 0->1->4->3 is used
    paths = token_network_model.get_paths(
        source=addresses[0],
        target=addresses[3],
        value=PaymentAmount(10),
        max_paths=1,
        reachability_state=reachability_state,
    )
    assert len(paths) == 1
    assert paths[0].to_dict() == {
        "path": [hex_addrs[0], hex_addrs[1], hex_addrs[4], hex_addrs[3]],
        "estimated_fee": 0,
    }

    # Not connected.
    no_paths = token_network_model.get_paths(
        source=addresses[0],
        target=addresses[5],
        value=PaymentAmount(10),
        max_paths=1,
        reachability_state=reachability_state,
    )
    assert [] == no_paths


@pytest.mark.usefixtures("populate_token_network_case_1")
def test_capacity_check(
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
):
    """ Test that the mediation fees are included in the capacity check """
    # First get a path without mediation fees. This must return the shortest path: 4->1->0
    paths = token_network_model.get_paths(
        source=addresses[4],
        target=addresses[0],
        value=PaymentAmount(35),
        max_paths=1,
        reachability_state=reachability_state,
    )
    index_paths = [addresses_to_indexes(p.nodes, addresses) for p in paths]
    assert index_paths == [[4, 1, 0]]

    # New let's add mediation fees to the channel 0->1.
    model_with_fees = deepcopy(token_network_model)
    model_with_fees.G[addresses[1]][addresses[0]]["view"].fee_schedule_sender.flat = 1
    # The transfer from 4->1 must now include 1 Token for the mediation fee
    # which will be payed for the 1->0 channel in addition to the payment
    # value of 35. But 35 + 1 exceeds the capacity for channel 4->1, which is
    # 35. So we should now get the next best route instead.
    paths = model_with_fees.get_paths(
        source=addresses[4],
        target=addresses[0],
        value=PaymentAmount(35),
        max_paths=1,
        reachability_state=reachability_state,
        fee_penalty=0,
    )
    index_paths = [addresses_to_indexes(p.nodes, addresses) for p in paths]
    assert index_paths == [[4, 1, 2, 0]]


@pytest.mark.usefixtures("populate_token_network_case_1")
def test_routing_result_order(
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
):
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    paths = token_network_model.get_paths(
        source=addresses[0],
        target=addresses[2],
        value=PaymentAmount(10),
        max_paths=5,
        reachability_state=reachability_state,
    )
    # 5 paths requested, but only 1 is available
    assert len(paths) == 1
    assert paths[0].to_dict() == {
        "path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]],
        "estimated_fee": 0,
    }


def addresses_to_indexes(path, addresses):
    index_of_address = {a: i for i, a in enumerate(addresses)}
    return [index_of_address[a] for a in path]


def get_paths(  # pylint: disable=too-many-arguments
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
    source_index: int = 0,
    target_index: int = 8,
    value: PaymentAmount = PaymentAmount(10),
    max_paths: int = 5,
    diversity_penalty: float = DIVERSITY_PEN_DEFAULT,
) -> List:
    paths = token_network_model.get_paths(
        diversity_penalty=diversity_penalty,
        source=addresses[source_index],
        target=addresses[target_index],
        value=value,
        max_paths=max_paths,
        reachability_state=reachability_state,
    )
    index_paths = [addresses_to_indexes(p.nodes, addresses) for p in paths]
    return index_paths


@pytest.mark.usefixtures("populate_token_network_case_3")
def test_diversity_penalty(
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
):
    """ Check changes in routing when increasing diversity penalty """

    assert get_paths(
        token_network_model=token_network_model,
        reachability_state=reachability_state,
        addresses=addresses,
        diversity_penalty=0.1,
    ) == [[0, 7, 8], [0, 7, 6, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8], [0, 1, 2, 3, 4, 8]]

    assert get_paths(
        token_network_model=token_network_model,
        reachability_state=reachability_state,
        addresses=addresses,
        diversity_penalty=1.1,
    ) == [[0, 7, 8], [0, 7, 6, 8], [0, 1, 2, 3, 4, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8]]

    assert get_paths(
        token_network_model=token_network_model,
        reachability_state=reachability_state,
        addresses=addresses,
        diversity_penalty=10,
    ) == [[0, 7, 8], [0, 1, 2, 3, 4, 8], [0, 7, 6, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8]]


@pytest.mark.usefixtures("populate_token_network_case_3")
def test_reachability_initiator(
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
):

    assert get_paths(
        token_network_model=token_network_model,
        reachability_state=reachability_state,
        addresses=addresses,
    ) == [[0, 7, 8], [0, 1, 2, 3, 4, 8], [0, 7, 6, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8]]

    reachability_state.reachabilities[addresses[0]] = AddressReachability.UNREACHABLE
    assert (
        get_paths(
            token_network_model=token_network_model,
            reachability_state=reachability_state,
            addresses=addresses,
        )
        == []
    )

    reachability_state.reachabilities[addresses[0]] = AddressReachability.UNKNOWN
    assert (
        get_paths(
            token_network_model=token_network_model,
            reachability_state=reachability_state,
            addresses=addresses,
        )
        == []
    )


@pytest.mark.usefixtures("populate_token_network_case_3")
def test_reachability_mediator(
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
):

    assert get_paths(
        token_network_model=token_network_model,
        reachability_state=reachability_state,
        addresses=addresses,
    ) == [[0, 7, 8], [0, 1, 2, 3, 4, 8], [0, 7, 6, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8]]

    reachability_state.reachabilities[addresses[7]] = AddressReachability.UNREACHABLE
    assert get_paths(
        token_network_model=token_network_model,
        reachability_state=reachability_state,
        addresses=addresses,
    ) == [[0, 1, 2, 3, 4, 8]]

    reachability_state.reachabilities[addresses[1]] = AddressReachability.UNKNOWN
    assert (
        get_paths(
            token_network_model=token_network_model,
            reachability_state=reachability_state,
            addresses=addresses,
        )
        == []
    )


@pytest.mark.usefixtures("populate_token_network_case_3")
def test_reachability_target(
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
):

    assert get_paths(
        token_network_model=token_network_model,
        reachability_state=reachability_state,
        addresses=addresses,
    ) == [[0, 7, 8], [0, 1, 2, 3, 4, 8], [0, 7, 6, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8]]

    reachability_state.reachabilities[addresses[8]] = AddressReachability.UNREACHABLE
    assert (
        get_paths(
            token_network_model=token_network_model,
            reachability_state=reachability_state,
            addresses=addresses,
        )
        == []
    )

    reachability_state.reachabilities[addresses[8]] = AddressReachability.UNKNOWN
    assert (
        get_paths(
            token_network_model=token_network_model,
            reachability_state=reachability_state,
            addresses=addresses,
        )
        == []
    )


@pytest.mark.skip("Just run it locally for now")
@pytest.mark.usefixtures("populate_token_network_random")
def test_routing_benchmark(token_network_model: TokenNetwork):  # pylint: disable=too-many-locals
    value = PaymentAmount(100)
    G = token_network_model.G
    addresses_to_reachabilities = SimpleReachabilityContainer(
        {
            node: random.choice(
                (
                    AddressReachability.REACHABLE,
                    AddressReachability.UNKNOWN,
                    AddressReachability.UNREACHABLE,
                )
            )
            for node in G.nodes
        }
    )

    times = []
    start = time.time()
    for _ in range(100):
        tic = time.time()
        source, target = random.sample(G.nodes, 2)
        paths = token_network_model.get_paths(
            source=source,
            target=target,
            value=value,
            max_paths=5,
            reachability_state=addresses_to_reachabilities,
        )

        toc = time.time()
        times.append(toc - tic)
    end = time.time()

    for path_object in paths:
        path = path_object.nodes
        fees = path_object.estimated_fee
        for node1, node2 in zip(path[:-1], path[1:]):
            view: ChannelView = G[to_canonical_address(node1)][to_canonical_address(node2)]["view"]
            print("capacity = ", view.capacity)
        print("fee sum = ", fees)
    print("Paths: ", paths)
    print("Mean runtime: ", sum(times) / len(times))
    print("Min runtime: ", min(times))
    print("Max runtime: ", max(times))
    print("Total runtime: ", end - start)


@pytest.mark.usefixtures("populate_token_network_case_2")
def test_suggest_partner(
    token_network_model: TokenNetwork, addresses: List[Address],
):
    a = addresses  # pylint: disable=invalid-name

    reachability = SimpleReachabilityContainer(
        {a[i]: AddressReachability.REACHABLE for i in range(3)}
    )
    suggestions = token_network_model.suggest_partner(reachability)
    assert len(suggestions) == 3
    assert set(s["address"] for s in suggestions) == set(
        to_checksum_address(a[i]) for i in range(3)
    )
    assert suggestions[0]["address"] == to_checksum_address(a[1])

    # Increasing uptime of node 0 should move it to first place
    reachability.times[a[0]] -= timedelta(seconds=10)
    suggestions = token_network_model.suggest_partner(reachability)
    assert suggestions[0]["address"] == to_checksum_address(a[0])

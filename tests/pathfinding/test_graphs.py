import random
import time
from typing import List

import pytest
from networkx import NetworkXNoPath

from pathfinding_service.model import ChannelView, TokenNetwork
from raiden.utils.typing import ChannelID, FeeAmount, TokenAmount
from raiden_libs.types import Address, TokenNetworkAddress


def test_edge_weight(addresses):
    channel_id = ChannelID(1)
    participant1 = addresses[0]
    participant2 = addresses[1]
    settle_timeout = 15
    view = ChannelView(
        TokenNetworkAddress("0x11"), channel_id, participant1, participant2, settle_timeout
    )
    amount = TokenAmount(int(1e18))  # one RDN

    # no penalty
    assert TokenNetwork.edge_weight(dict(), dict(view=view), amount=amount, fee_penalty=0) == 1

    # channel already used in a previous route
    assert (
        TokenNetwork.edge_weight({channel_id: 2}, dict(view=view), amount=amount, fee_penalty=0)
        == 3
    )

    # absolute fee
    view.absolute_fee = FeeAmount(int(0.03e18))
    assert TokenNetwork.edge_weight(dict(), dict(view=view), amount=amount, fee_penalty=100) == 4

    # relative fee
    view.absolute_fee = FeeAmount(0)
    view.relative_fee = 0.01
    assert TokenNetwork.edge_weight(dict(), dict(view=view), amount=amount, fee_penalty=100) == 2


@pytest.mark.usefixtures("populate_token_network_random")
def test_routing_benchmark(token_network_model: TokenNetwork):
    value = TokenAmount(100)
    G = token_network_model.G
    times = []
    start = time.time()
    for _ in range(100):
        tic = time.time()
        source, target = random.sample(G.nodes, 2)
        paths = token_network_model.get_paths(source, target, value=value, max_paths=5)
        toc = time.time()
        times.append(toc - tic)
    end = time.time()
    for path_object in paths:
        path = path_object["path"]
        fees = path_object["estimated_fee"]
        for node1, node2 in zip(path[:-1], path[1:]):
            view: ChannelView = G[node1][node2]["view"]
            print("fee = ", view.absolute_fee, "capacity = ", view.capacity)
        print("fee sum = ", fees)
    print("Paths: ", paths)
    print("Mean runtime: ", sum(times) / len(times))
    print("Min runtime: ", min(times))
    print("Max runtime: ", max(times))
    print("Total runtime: ", end - start)


@pytest.mark.usefixtures("populate_token_network_case_1")
def test_routing_simple(token_network_model: TokenNetwork, addresses: List[Address]):
    view01: ChannelView = token_network_model.G[addresses[0]][addresses[1]]["view"]
    view10: ChannelView = token_network_model.G[addresses[1]][addresses[0]]["view"]

    assert view01.deposit == 100
    assert view01.absolute_fee == 0
    assert view01.capacity == 90
    assert view10.capacity == 60

    # 0->2->3 is the shortest path, but has no capacity, so 0->1->4->3 is used
    paths = token_network_model.get_paths(
        addresses[0], addresses[3], value=TokenAmount(10), max_paths=1
    )
    assert len(paths) == 1
    assert paths[0] == {
        "path": [addresses[0], addresses[1], addresses[4], addresses[3]],
        "estimated_fee": 0,
    }

    # Not connected.
    with pytest.raises(NetworkXNoPath):
        token_network_model.get_paths(
            addresses[0], addresses[5], value=TokenAmount(10), max_paths=1
        )


@pytest.mark.usefixtures("populate_token_network_case_1")
def test_routing_result_order(token_network_model: TokenNetwork, addresses: List[Address]):
    paths = token_network_model.get_paths(
        addresses[0], addresses[2], value=TokenAmount(10), max_paths=5
    )
    # 5 paths requested, but only 1 is available
    assert len(paths) == 1
    assert paths[0] == {"path": [addresses[0], addresses[1], addresses[2]], "estimated_fee": 0}


def addresses_to_indexes(path, addresses):
    index_of_address = {a: i for i, a in enumerate(addresses)}
    return [index_of_address[a] for a in path]


@pytest.mark.usefixtures("populate_token_network_case_3")
def test_diversity_penalty(token_network_model: TokenNetwork, addresses: List[Address]):
    """ Check changes in routing when increasing diversity penalty """

    def get_paths(diversity_penalty):
        paths = token_network_model.get_paths(
            addresses[0],
            addresses[8],
            value=TokenAmount(10),
            max_paths=5,
            diversity_penalty=diversity_penalty,
        )
        index_paths = [addresses_to_indexes(p["path"], addresses) for p in paths]
        return index_paths

    assert get_paths(0.1) == [
        [0, 7, 8],
        [0, 7, 6, 8],
        [0, 7, 9, 10, 8],
        [0, 7, 6, 5, 8],
        [0, 1, 2, 3, 4, 8],
    ]

    assert get_paths(1.1) == [
        [0, 7, 8],
        [0, 7, 6, 8],
        [0, 1, 2, 3, 4, 8],
        [0, 7, 9, 10, 8],
        [0, 7, 6, 5, 8],
    ]

    assert get_paths(10) == [
        [0, 7, 8],
        [0, 1, 2, 3, 4, 8],
        [0, 7, 6, 8],
        [0, 7, 9, 10, 8],
        [0, 7, 6, 5, 8],
    ]

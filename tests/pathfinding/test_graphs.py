from copy import deepcopy
from typing import Dict, List

import pytest
from eth_utils import decode_hex, to_checksum_address
from networkx import NetworkXNoPath

from pathfinding_service.config import DIVERSITY_PEN_DEFAULT
from pathfinding_service.model import ChannelView, TokenNetwork
from raiden.network.transport.matrix import AddressReachability
from raiden.utils.typing import Address, ChannelID, FeeAmount, TokenAmount, TokenNetworkAddress


def test_edge_weight(addresses):
    # pylint: disable=assigning-non-slot
    channel_id = ChannelID(1)
    participant1 = addresses[0]
    participant2 = addresses[1]
    capacity = TokenAmount(int(20 * 1e18))
    capacity_partner = TokenAmount(int(10 * 1e18))
    settle_timeout = 15
    view = ChannelView(
        token_network_address=TokenNetworkAddress(bytes([1])),
        channel_id=channel_id,
        participant1=participant1,
        participant2=participant2,
        capacity=capacity,
        settle_timeout=settle_timeout,
    )
    view_partner = ChannelView(
        token_network_address=TokenNetworkAddress(bytes([1])),
        channel_id=channel_id,
        participant1=participant2,
        participant2=participant1,
        capacity=capacity_partner,
        settle_timeout=settle_timeout,
    )
    amount = TokenAmount(int(1e18))  # one RDN

    # no penalty
    assert (
        TokenNetwork.edge_weight(
            dict(), dict(view=view), dict(view=view_partner), amount=amount, fee_penalty=0
        )
        == 1
    )

    # channel already used in a previous route
    assert (
        TokenNetwork.edge_weight(
            {channel_id: 2}, dict(view=view), dict(view=view_partner), amount=amount, fee_penalty=0
        )
        == 3
    )

    # absolute fee
    view.fee_schedule_sender.flat = FeeAmount(int(0.03e18))
    assert (
        TokenNetwork.edge_weight(
            dict(), dict(view=view), dict(view=view_partner), amount=amount, fee_penalty=100
        )
        == 4
    )

    # relative fee
    view.fee_schedule_sender.flat = FeeAmount(0)
    view.fee_schedule_sender.proportional = 0.01
    assert (
        TokenNetwork.edge_weight(
            dict(), dict(view=view), dict(view=view_partner), amount=amount, fee_penalty=100
        )
        == 2
    )

    # partner has not enough capacity for refund (no_refund_weight) -> edge weight +1
    view_partner.capacity = TokenAmount(0)
    assert (
        TokenNetwork.edge_weight(
            dict(), dict(view=view), dict(view=view_partner), amount=amount, fee_penalty=100
        )
        == 3
    )


@pytest.mark.usefixtures("populate_token_network_case_1")
def test_routing_simple(
    token_network_model: TokenNetwork,
    address_to_reachability: Dict[Address, AddressReachability],
    addresses: List[Address],
):
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    view01: ChannelView = token_network_model.G[addresses[0]][addresses[1]]["view"]
    view10: ChannelView = token_network_model.G[addresses[1]][addresses[0]]["view"]

    assert view01.deposit == 100
    assert view01.fee_schedule_sender.flat == 0
    assert view01.capacity == 90
    assert view10.capacity == 60

    # 0->2->3 is the shortest path, but has no capacity, so 0->1->4->3 is used
    paths = token_network_model.get_paths(
        source=addresses[0],
        target=addresses[3],
        value=TokenAmount(10),
        max_paths=1,
        address_to_reachability=address_to_reachability,
    )
    assert len(paths) == 1
    assert paths[0] == {
        "path": [hex_addrs[0], hex_addrs[1], hex_addrs[4], hex_addrs[3]],
        "estimated_fee": 0,
    }

    # Not connected.
    with pytest.raises(NetworkXNoPath):
        token_network_model.get_paths(
            source=addresses[0],
            target=addresses[5],
            value=TokenAmount(10),
            max_paths=1,
            address_to_reachability=address_to_reachability,
        )


@pytest.mark.usefixtures("populate_token_network_case_1")
def test_capacity_check(
    token_network_model: TokenNetwork,
    address_to_reachability: Dict[Address, AddressReachability],
    addresses: List[Address],
):
    """ Test that the mediation fees are included in the capacity check """
    # First get a path without mediation fees. This must return the shortest path: 4->1->0
    paths = token_network_model.get_paths(
        addresses[4],
        addresses[0],
        value=TokenAmount(35),
        max_paths=1,
        address_to_reachability=address_to_reachability,
    )
    index_paths = [addresses_to_indexes(p["path"], addresses) for p in paths]
    assert index_paths == [[4, 1, 0]]

    # New let's add mediation fees to the channel 0->1.
    model_with_fees = deepcopy(token_network_model)
    model_with_fees.G[addresses[1]][addresses[0]]["view"].fee_schedule_sender.flat = 1
    # The transfer from 4->1 must now include 1 Token for the mediation fee
    # which will be payed for the 1->0 channel in addition to the payment
    # value of 35. But 35 + 1 exceeds the capacity for channel 4->1, which is
    # 35. So we should now get the next best route instead.
    paths = model_with_fees.get_paths(
        addresses[4],
        addresses[0],
        value=TokenAmount(35),
        max_paths=1,
        address_to_reachability=address_to_reachability,
        fee_penalty=0,
    )
    index_paths = [addresses_to_indexes(p["path"], addresses) for p in paths]
    assert index_paths == [[4, 1, 2, 0]]


@pytest.mark.usefixtures("populate_token_network_case_1")
def test_routing_result_order(
    token_network_model: TokenNetwork,
    address_to_reachability: Dict[Address, AddressReachability],
    addresses: List[Address],
):
    hex_addrs = [to_checksum_address(addr) for addr in addresses]
    paths = token_network_model.get_paths(
        addresses[0],
        addresses[2],
        value=TokenAmount(10),
        max_paths=5,
        address_to_reachability=address_to_reachability,
    )
    # 5 paths requested, but only 1 is available
    assert len(paths) == 1
    assert paths[0] == {"path": [hex_addrs[0], hex_addrs[1], hex_addrs[2]], "estimated_fee": 0}


def addresses_to_indexes(path, addresses):
    index_of_address = {a: i for i, a in enumerate(addresses)}
    return [index_of_address[decode_hex(a)] for a in path]


def get_paths(  # pylint: disable=too-many-arguments
    token_network_model: TokenNetwork,
    address_to_reachability: Dict[Address, AddressReachability],
    addresses: List[Address],
    source_index: int = 0,
    target_index: int = 8,
    value: TokenAmount = TokenAmount(10),
    max_paths: int = 5,
    diversity_penalty: float = DIVERSITY_PEN_DEFAULT,
) -> List:
    paths = token_network_model.get_paths(
        diversity_penalty=diversity_penalty,
        source=addresses[source_index],
        target=addresses[target_index],
        value=value,
        max_paths=max_paths,
        address_to_reachability=address_to_reachability,
    )
    index_paths = [addresses_to_indexes(p["path"], addresses) for p in paths]
    return index_paths


@pytest.mark.usefixtures("populate_token_network_case_3")
def test_diversity_penalty(
    token_network_model: TokenNetwork,
    address_to_reachability: Dict[Address, AddressReachability],
    addresses: List[Address],
):
    """ Check changes in routing when increasing diversity penalty """

    assert get_paths(
        token_network_model=token_network_model,
        address_to_reachability=address_to_reachability,
        addresses=addresses,
        diversity_penalty=0.1,
    ) == [[0, 7, 8], [0, 7, 6, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8], [0, 1, 2, 3, 4, 8]]

    assert get_paths(
        token_network_model=token_network_model,
        address_to_reachability=address_to_reachability,
        addresses=addresses,
        diversity_penalty=1.1,
    ) == [[0, 7, 8], [0, 7, 6, 8], [0, 1, 2, 3, 4, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8]]

    assert get_paths(
        token_network_model=token_network_model,
        address_to_reachability=address_to_reachability,
        addresses=addresses,
        diversity_penalty=10,
    ) == [[0, 7, 8], [0, 1, 2, 3, 4, 8], [0, 7, 6, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8]]


@pytest.mark.usefixtures("populate_token_network_case_3")
def test_reachability_initiator(
    token_network_model: TokenNetwork,
    address_to_reachability: Dict[Address, AddressReachability],
    addresses: List[Address],
):

    assert get_paths(
        token_network_model=token_network_model,
        address_to_reachability=address_to_reachability,
        addresses=addresses,
    ) == [[0, 7, 8], [0, 1, 2, 3, 4, 8], [0, 7, 6, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8]]

    address_to_reachability[addresses[0]] = AddressReachability.UNREACHABLE
    assert (
        get_paths(
            token_network_model=token_network_model,
            address_to_reachability=address_to_reachability,
            addresses=addresses,
        )
        == []
    )

    address_to_reachability[addresses[0]] = AddressReachability.UNKNOWN
    assert (
        get_paths(
            token_network_model=token_network_model,
            address_to_reachability=address_to_reachability,
            addresses=addresses,
        )
        == []
    )


@pytest.mark.usefixtures("populate_token_network_case_3")
def test_reachability_mediator(
    token_network_model: TokenNetwork,
    address_to_reachability: Dict[Address, AddressReachability],
    addresses: List[Address],
):

    assert get_paths(
        token_network_model=token_network_model,
        address_to_reachability=address_to_reachability,
        addresses=addresses,
    ) == [[0, 7, 8], [0, 1, 2, 3, 4, 8], [0, 7, 6, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8]]

    address_to_reachability[addresses[7]] = AddressReachability.UNREACHABLE
    assert get_paths(
        token_network_model=token_network_model,
        address_to_reachability=address_to_reachability,
        addresses=addresses,
    ) == [[0, 1, 2, 3, 4, 8]]

    address_to_reachability[addresses[1]] = AddressReachability.UNKNOWN
    assert (
        get_paths(
            token_network_model=token_network_model,
            address_to_reachability=address_to_reachability,
            addresses=addresses,
        )
        == []
    )


@pytest.mark.usefixtures("populate_token_network_case_3")
def test_reachability_target(
    token_network_model: TokenNetwork,
    address_to_reachability: Dict[Address, AddressReachability],
    addresses: List[Address],
):

    assert get_paths(
        token_network_model=token_network_model,
        address_to_reachability=address_to_reachability,
        addresses=addresses,
    ) == [[0, 7, 8], [0, 1, 2, 3, 4, 8], [0, 7, 6, 8], [0, 7, 9, 10, 8], [0, 7, 6, 5, 8]]

    address_to_reachability[addresses[8]] = AddressReachability.UNREACHABLE
    assert (
        get_paths(
            token_network_model=token_network_model,
            address_to_reachability=address_to_reachability,
            addresses=addresses,
        )
        == []
    )

    address_to_reachability[addresses[8]] = AddressReachability.UNKNOWN
    assert (
        get_paths(
            token_network_model=token_network_model,
            address_to_reachability=address_to_reachability,
            addresses=addresses,
        )
        == []
    )

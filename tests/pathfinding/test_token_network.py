from typing import List

from networkx import DiGraph

from pathfinding_service.model import TokenNetwork
from pathfinding_service.model.token_network import Path, prune_graph
from raiden.network.transport.matrix import AddressReachability
from raiden.tests.utils.factories import make_address
from raiden.utils.typing import Address, BlockTimeout, ChannelID, PaymentAmount

from .utils import SimpleReachabilityContainer


def test_tn_idempotency_of_channel_openings(
    token_network_model: TokenNetwork, addresses: List[Address]
):
    # create same channel 5 times
    for _ in range(5):
        token_network_model.handle_channel_opened_event(
            channel_identifier=ChannelID(1),
            participant1=addresses[0],
            participant2=addresses[1],
            settle_timeout=BlockTimeout(15),
        )
    # there should only be one channel
    assert len(token_network_model.channel_id_to_addresses) == 1

    # now close the channel
    token_network_model.handle_channel_removed_event(channel_identifier=ChannelID(1))

    # there should be no channels
    assert len(token_network_model.channel_id_to_addresses) == 0


def test_tn_multiple_channels_for_two_participants_opened(
    token_network_model: TokenNetwork, addresses: List[Address]
):
    token_network_model.handle_channel_opened_event(
        channel_identifier=ChannelID(1),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=BlockTimeout(15),
    )
    token_network_model.handle_channel_opened_event(
        channel_identifier=ChannelID(2),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=BlockTimeout(15),
    )

    # now there should be two channels
    assert len(token_network_model.channel_id_to_addresses) == 2

    # now close one channel
    token_network_model.handle_channel_removed_event(channel_identifier=ChannelID(1))

    # there should be one channel left
    assert len(token_network_model.channel_id_to_addresses) == 1


def test_graph_pruning():
    participant1 = make_address()
    participant2 = make_address()
    participant3 = make_address()

    graph = DiGraph()
    graph.add_edge(participant1, participant2, view=12)
    graph.add_edge(participant2, participant1, view=21)
    graph.add_edge(participant2, participant3, view=23)
    graph.add_edge(participant3, participant2, view=32)

    all_reachable = SimpleReachabilityContainer(
        {p: AddressReachability.REACHABLE for p in (participant1, participant2, participant3)}
    )
    pruned_all_reachable = prune_graph(graph=graph, reachability_state=all_reachable)
    assert len(pruned_all_reachable.edges) == len(graph.edges)

    p1_not_reachable = SimpleReachabilityContainer(all_reachable.reachabilities.copy())
    p1_not_reachable.reachabilities[participant1] = AddressReachability.UNREACHABLE
    pruned_p1_unreachbale = prune_graph(graph=graph, reachability_state=p1_not_reachable)
    assert len(pruned_p1_unreachbale.edges) == 2  # just the two edges between 2 and 3 left

    p2_not_reachable = SimpleReachabilityContainer(all_reachable.reachabilities.copy())
    p2_not_reachable.reachabilities[participant1] = AddressReachability.UNREACHABLE
    p2_not_reachable.reachabilities[participant2] = AddressReachability.UNREACHABLE
    pruned_p2_unreachbale = prune_graph(graph=graph, reachability_state=p2_not_reachable)
    assert len(pruned_p2_unreachbale.edges) == 0  # 2 is part of all channels

    # test handling of unknown nodes
    p1_not_in_reachble_map = SimpleReachabilityContainer(all_reachable.reachabilities.copy())
    del p1_not_in_reachble_map.reachabilities[participant1]
    pruned_p1_not_in_reachable_map = prune_graph(
        graph=graph, reachability_state=p1_not_in_reachble_map
    )
    assert (
        len(pruned_p1_not_in_reachable_map.edges) == 2
    )  # just the two edges between 2 and 3 left


def test_path_without_capacity(token_network_model: TokenNetwork, addresses: List[Address]):
    """Channels without capacity must not cause unexpected exceptions.

    Regression test for https://github.com/raiden-network/raiden-services/issues/636
    """
    token_network_model.handle_channel_opened_event(
        channel_identifier=ChannelID(1),
        participant1=addresses[0],
        participant2=addresses[1],
        settle_timeout=BlockTimeout(15),
    )
    token_network_model.handle_channel_opened_event(
        channel_identifier=ChannelID(2),
        participant1=addresses[1],
        participant2=addresses[2],
        settle_timeout=BlockTimeout(15),
    )

    token_network_model.G[addresses[1]][addresses[2]]["view"].channel.capacity1 = 100
    path = Path(
        G=token_network_model.G,
        nodes=[addresses[0], addresses[1], addresses[2]],
        value=PaymentAmount(10),
        reachability_state=SimpleReachabilityContainer({}),
    )
    assert not path.is_valid


def test_check_path_request_errors(token_network_model, addresses):
    a = addresses  # pylint: disable=invalid-name

    # Not online checks
    assert (
        token_network_model.check_path_request_errors(
            a[0], a[2], 100, SimpleReachabilityContainer({})
        )
        == "Source not online"
    )
    assert (
        token_network_model.check_path_request_errors(
            a[0], a[2], 100, SimpleReachabilityContainer({a[0]: AddressReachability.REACHABLE})
        )
        == "Target not online"
    )

    # No channel checks
    reachability = SimpleReachabilityContainer(
        {a[0]: AddressReachability.REACHABLE, a[2]: AddressReachability.REACHABLE}
    )
    assert (
        token_network_model.check_path_request_errors(a[0], a[2], 100, reachability)
        == "No channel from source"
    )
    token_network_model.handle_channel_opened_event(
        channel_identifier=ChannelID(1),
        participant1=a[0],
        participant2=a[1],
        settle_timeout=BlockTimeout(15),
    )
    assert (
        token_network_model.check_path_request_errors(a[0], a[2], 100, reachability)
        == "No channel to target"
    )
    token_network_model.handle_channel_opened_event(
        channel_identifier=ChannelID(1),
        participant1=a[1],
        participant2=a[2],
        settle_timeout=BlockTimeout(15),
    )

    # Check capacities
    assert token_network_model.check_path_request_errors(a[0], a[2], 100, reachability).startswith(
        "Source does not have a channel with sufficient capacity"
    )
    token_network_model.G.edges[a[0], a[1]]["view"].capacity = 100

    assert token_network_model.check_path_request_errors(a[0], a[2], 100, reachability).startswith(
        "Target does not have a channel with sufficient capacity"
    )
    token_network_model.G.edges[a[1], a[2]]["view"].capacity = 100

    # Must return `None` when no errors could be found
    assert token_network_model.check_path_request_errors(a[0], a[2], 100, reachability) is None

    # Check error when there is no route in the graph
    token_network_model.handle_channel_opened_event(
        channel_identifier=ChannelID(2),
        participant1=a[3],
        participant2=a[4],
        settle_timeout=BlockTimeout(15),
    )
    token_network_model.G.edges[a[3], a[4]]["view"].capacity = 100
    reachability.reachabilities[a[4]] = AddressReachability.REACHABLE
    assert (
        token_network_model.check_path_request_errors(a[0], a[4], 100, reachability)
        == "No route from source to target"
    )

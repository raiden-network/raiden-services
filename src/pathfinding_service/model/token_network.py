from collections import defaultdict
from datetime import datetime, timedelta, timezone
from itertools import islice
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import networkx as nx
import structlog
from eth_utils import to_checksum_address
from networkx import DiGraph
from networkx.exception import NetworkXNoPath, NodeNotFound

from pathfinding_service.constants import (
    DEFAULT_SETTLE_TO_REVEAL_TIMEOUT_RATIO,
    DIVERSITY_PEN_DEFAULT,
    FEE_PEN_DEFAULT,
)
from pathfinding_service.exceptions import InvalidPFSFeeUpdate
from pathfinding_service.model.channel import Channel, ChannelView, FeeSchedule
from raiden.exceptions import UndefinedMediationFee
from raiden.messages.path_finding_service import PFSCapacityUpdate, PFSFeeUpdate
from raiden.network.transport.matrix import AddressReachability
from raiden.utils.typing import (
    Address,
    Balance,
    ChannelID,
    FeeAmount,
    PaymentAmount,
    PaymentWithFeeAmount,
    TokenAmount,
    TokenNetworkAddress,
)

log = structlog.get_logger(__name__)


def prune_graph(
    graph: DiGraph, address_to_reachability: Dict[Address, AddressReachability]
) -> DiGraph:
    """ Prunes the given `graph` of all channels where the participants are not  reachable. """
    pruned_graph = DiGraph()
    for p1, p2 in graph.edges:
        nodes_online = (
            address_to_reachability.get(p1) == AddressReachability.REACHABLE
            and address_to_reachability.get(p2) == AddressReachability.REACHABLE
        )
        if nodes_online:
            pruned_graph.add_edge(p1, p2, view=graph[p1][p2]["view"])
            pruned_graph.add_edge(p2, p1, view=graph[p2][p1]["view"])

    return pruned_graph


def window(seq: Sequence, n: int = 2) -> Iterable[tuple]:
    """Returns a sliding window (of width n) over data from the iterable
    s -> (s0,s1,...s[n-1]), (s1,s2,...,sn), ...
    See https://stackoverflow.com/a/6822773/114926
    """
    remaining_elements = iter(seq)
    result = tuple(islice(remaining_elements, n))
    if len(result) == n:
        yield result
    for elem in remaining_elements:
        result = result[1:] + (elem,)
        yield result


class Path:
    def __init__(
        self,
        G: DiGraph,
        nodes: List[Address],
        value: PaymentAmount,
        address_to_reachability: Dict[Address, AddressReachability],
    ):
        self.G = G
        self.nodes = nodes
        self.value = value
        self.address_to_reachability = address_to_reachability
        self.fees: List[FeeAmount] = []
        self._calculate_fees()

        log.debug("Creating Path object", nodes=nodes, is_valid=self.is_valid, fees=self.fees)

    def _calculate_fees(self) -> None:
        total = PaymentWithFeeAmount(self.value)
        for prev_node, mediator, next_node in reversed(list(window(self.nodes, 3))):
            try:
                view_in: ChannelView = self.G[prev_node][mediator]["view"]
                view_out: ChannelView = self.G[mediator][next_node]["view"]

                fee_out = view_out.backwards_fee_sender(
                    balance=Balance(view_out.capacity), amount=total
                )

                total += fee_out  # type: ignore

                fee_in = view_in.backwards_fee_receiver(
                    balance=Balance(view_in.capacity), amount=total
                )

                total += fee_in  # type: ignore

                self.fees.append(FeeAmount(fee_in + fee_out))
            except UndefinedMediationFee:
                log.warning(
                    "Invalid fee calculation",
                    amount=total,
                    view_out=view_out,
                    view_in=view_in,
                    fee_schedule_sender=view_out.fee_schedule_sender,
                    fee_schedule_receiver=view_in.fee_schedule_receiver,
                )
                self._is_valid = False

    @property
    def edge_attrs(self) -> Iterable[dict]:
        return (self.G[node1][node2] for node1, node2 in zip(self.nodes[:-1], self.nodes[1:]))

    def to_dict(self) -> dict:
        return dict(
            path=[to_checksum_address(node) for node in self.nodes], estimated_fee=sum(self.fees)
        )

    @property
    def is_valid(self) -> bool:
        """ Check capacity and settle timeout

        Capacity: The capacity for the last channel must be at least
        the payment value. The previous channel's capacity has to be larger
        than value + last channel's capacity, etc.

        Settle timeout: The raiden client will not forward payments if the
        channel over which they receive has a too low settle_timeout. So we
        should not use such routes. See
        https://github.com/raiden-network/raiden-services/issues/5.
        """
        log.debug("Checking path validity", nodes=self.nodes, value=self.value)
        if hasattr(self, "_is_valid"):
            return self._is_valid
        required_capacity = self.value
        edges = reversed(list(self.edge_attrs))
        fees = self.fees + [FeeAmount(0)]  # The hop to the target does not incur mediation fees
        for edge, fee in zip(edges, fees):
            # check capacity
            if edge["view"].capacity < required_capacity:
                log.debug(
                    "Path invalid because of missing capacity",
                    edge=edge,
                    fee=fees,
                    available_capacity=edge["view"].capacity,
                    required_capacity=required_capacity,
                )
                return False
            required_capacity = PaymentAmount(required_capacity + fee)

            # check if settle_timeout / reveal_timeout >= default ratio
            ratio = edge["view"].settle_timeout / edge["view"].reveal_timeout
            if ratio < DEFAULT_SETTLE_TO_REVEAL_TIMEOUT_RATIO:
                log.debug(
                    "Path invalid because of too low reveal timeout ratio",
                    edge=edge,
                    fee=fees,
                    settle_timeout=edge["view"].settle_timeout,
                    reveal_timeout=edge["view"].reveal_timeout,
                    ratio=ratio,
                    required_ratio=DEFAULT_SETTLE_TO_REVEAL_TIMEOUT_RATIO,
                )
                return False

        # check node reachabilities
        for node in self.nodes:
            node_reachability = self.address_to_reachability.get(node, AddressReachability.UNKNOWN)
            if node_reachability != AddressReachability.REACHABLE:
                log.debug(
                    "Path invalid because of unavailable node",
                    node=node,
                    node_reachability=node_reachability,
                )
                return False

        return True


class TokenNetwork:
    """ Manages a token network for pathfinding. """

    def __init__(self, token_network_address: TokenNetworkAddress):
        """ Initializes a new TokenNetwork. """

        self.address = token_network_address
        self.channel_id_to_addresses: Dict[ChannelID, Tuple[Address, Address]] = dict()
        self.G = DiGraph()

    def __repr__(self) -> str:
        return (
            f"<TokenNetwork address = {self.address} "
            f"num_channels = {len(self.channel_id_to_addresses)}>"
        )

    #
    # Contract event listener functions
    #

    def handle_channel_opened_event(
        self,
        channel_identifier: ChannelID,
        participant1: Address,
        participant2: Address,
        settle_timeout: int,
    ) -> Channel:
        """ Register the channel in the graph, add participants to graph if necessary.

        Corresponds to the ChannelOpened event. Called by the contract event listener.
        We swap participants unless participant1 < participant2."""

        if participant1 > participant2:
            (participant1, participant2) = (participant2, participant1)

        channel = Channel(
            token_network_address=self.address,
            channel_id=channel_identifier,
            participant1=participant1,
            participant2=participant2,
            settle_timeout=settle_timeout,
        )
        views = channel.views

        for cv in views:
            self.add_channel_view(cv)

        return channel

    def add_channel_view(self, channel_view: ChannelView) -> None:
        # Only add it once per channel, not once per ChannelView
        if channel_view.participant1 < channel_view.participant2:
            self.channel_id_to_addresses[channel_view.channel_id] = (
                channel_view.participant1,
                channel_view.participant2,
            )
        self.G.add_edge(channel_view.participant1, channel_view.participant2, view=channel_view)

    def handle_channel_closed_event(self, channel_identifier: ChannelID) -> None:
        """ Close a channel. This doesn't mean that the channel is settled yet, but it cannot
        transfer any more.

        Corresponds to the ChannelClosed event. Called by the contract event listener. """

        try:
            # we need to unregister the channel_id here
            participant1, participant2 = self.channel_id_to_addresses.pop(channel_identifier)

            self.G.remove_edge(participant1, participant2)
            self.G.remove_edge(participant2, participant1)
        except KeyError:
            log.error(
                "Received ChannelClosed event for unknown channel",
                channel_identifier=channel_identifier,
            )

    def get_channel_views_for_partner(
        self, updating_participant: Address, other_participant: Address
    ) -> Tuple[ChannelView, ChannelView]:
        # Get the channel views from the perspective of the updating participant
        channel_view_to_partner = self.G[updating_participant][other_participant]["view"]
        channel_view_from_partner = self.G[other_participant][updating_participant]["view"]

        return channel_view_to_partner, channel_view_from_partner

    def handle_channel_balance_update_message(
        self,
        message: PFSCapacityUpdate,
        updating_capacity_partner: TokenAmount,
        other_capacity_partner: TokenAmount,
    ) -> Channel:
        """ Sends Capacity Update to PFS including the reveal timeout """
        channel_view_to_partner, channel_view_from_partner = self.get_channel_views_for_partner(
            updating_participant=message.updating_participant,
            other_participant=message.other_participant,
        )
        channel_view_to_partner.update_capacity(
            nonce=message.updating_nonce,
            capacity=min(message.updating_capacity, other_capacity_partner),
            reveal_timeout=message.reveal_timeout,
        )
        channel_view_from_partner.update_capacity(
            nonce=message.other_nonce,
            capacity=min(message.other_capacity, updating_capacity_partner),
        )
        return channel_view_to_partner.channel

    def handle_channel_fee_update(self, message: PFSFeeUpdate) -> Channel:
        if message.timestamp > datetime.now(timezone.utc) + timedelta(hours=1):
            # We don't really care about the time, but if we accept a time far
            # in the future, the client will have problems sending fee updates
            # with increasing time after fixing his clock.
            raise InvalidPFSFeeUpdate("Timestamp is in the future")
        channel_id = message.canonical_identifier.channel_identifier
        participants = self.channel_id_to_addresses[channel_id]
        other_participant = (set(participants) - {message.updating_participant}).pop()
        channel_view_to_partner, channel_view_from_partner = self.get_channel_views_for_partner(
            updating_participant=message.updating_participant, other_participant=other_participant
        )
        fee_schedule = FeeSchedule.from_raiden(message.fee_schedule, timestamp=message.timestamp)
        channel_view_to_partner.set_fee_schedule(fee_schedule)
        return channel_view_from_partner.channel

    @staticmethod
    def edge_weight(
        visited: Dict[ChannelID, float],
        view: ChannelView,
        view_from_partner: ChannelView,
        amount: PaymentAmount,
        fee_penalty: float,
    ) -> float:
        diversity_weight = visited.get(view.channel_id, 0)
        # Fees for initiator and target are included here. This promotes routes
        # that are nice to the initiator's and target's capacities, but it's
        # inconsistent with the estimated total fee.
        try:
            fee_out = view.backwards_fee_sender(
                balance=Balance(view.capacity), amount=PaymentWithFeeAmount(amount)
            )

            fee_in = view.backwards_fee_receiver(
                balance=Balance(view.capacity), amount=PaymentWithFeeAmount(amount)
            )

            fee_weight = (fee_in + fee_out) / 1e18 * fee_penalty
        except UndefinedMediationFee:
            return float("inf")
        no_refund_weight = 0
        if view_from_partner.capacity < int(float(amount) * 1.1):
            no_refund_weight = 1
        return 1 + diversity_weight + fee_weight + no_refund_weight

    def _get_single_path(  # pylint: disable=too-many-arguments, too-many-locals
        self,
        graph: DiGraph,
        source: Address,
        target: Address,
        value: PaymentAmount,
        address_to_reachability: Dict[Address, AddressReachability],
        visited: Dict[ChannelID, float],
        disallowed_paths: List[List[Address]],
        fee_penalty: float,
    ) -> Optional[Path]:
        # update edge weights
        for node1, node2 in graph.edges():
            edge = graph[node1][node2]
            backwards_edge = graph[node2][node1]
            edge["weight"] = self.edge_weight(
                visited=visited,
                view=edge["view"],
                view_from_partner=backwards_edge["view"],
                amount=value,
                fee_penalty=fee_penalty,
            )

        # find next path
        all_paths: Iterable[List[Address]] = nx.shortest_simple_paths(
            G=graph, source=source, target=target, weight="weight"
        )
        try:
            # skip duplicates and invalid paths
            path = next(
                p
                for p in (
                    Path(self.G, nodes, value, address_to_reachability) for nodes in all_paths
                )
                if p.is_valid and p.nodes not in disallowed_paths
            )
            return path
        except StopIteration:
            return None

    def get_paths(  # pylint: disable=too-many-arguments, too-many-locals
        self,
        source: Address,
        target: Address,
        value: PaymentAmount,
        max_paths: int,
        address_to_reachability: Dict[Address, AddressReachability],
        diversity_penalty: float = DIVERSITY_PEN_DEFAULT,
        fee_penalty: float = FEE_PEN_DEFAULT,
    ) -> List[dict]:
        """ Find best routes according to given preferences

        value: Amount of transferred tokens. Used for capacity checks
        diversity_penalty: One previously used channel is as bad as X more hops
        fee_penalty: One RDN in fees is as bad as X more hops
        """
        visited: Dict[ChannelID, float] = defaultdict(lambda: 0)
        paths: List[Path] = []

        log.debug(
            "Finding paths for payment",
            source=source,
            target=target,
            value=value,
            max_paths=max_paths,
            diversity_penalty=diversity_penalty,
            fee_penalty=fee_penalty,
            reachabilities=address_to_reachability,
        )

        # TODO: improve the pruning
        # Currently we make a snapshot of the currently reachable nodes, so the searched graph
        # becomes smaller
        pruned_graph = prune_graph(graph=self.G, address_to_reachability=address_to_reachability)

        while len(paths) < max_paths:
            try:
                path = self._get_single_path(
                    graph=pruned_graph,
                    source=source,
                    target=target,
                    value=value,
                    address_to_reachability=address_to_reachability,
                    visited=visited,
                    disallowed_paths=[p.nodes for p in paths],
                    fee_penalty=fee_penalty,
                )
            except (NetworkXNoPath, NodeNotFound):
                return []

            if path is None:
                break
            paths.append(path)

            # update visited penalty dict
            for edge in path.edge_attrs:
                channel_id = edge["view"].channel_id
                visited[channel_id] += diversity_penalty

        found_paths = [p.to_dict() for p in paths]
        log.info(
            "Returning paths for payment",
            source=source,
            target=target,
            value=value,
            max_paths=max_paths,
            diversity_penalty=diversity_penalty,
            fee_penalty=fee_penalty,
            paths=found_paths,
        )
        return found_paths

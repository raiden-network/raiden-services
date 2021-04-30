from collections import defaultdict
from copy import copy
from datetime import datetime, timedelta
from itertools import islice
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

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
from pathfinding_service.exceptions import InconsistentInternalState, InvalidFeeUpdate
from pathfinding_service.model.channel import Channel, ChannelView, FeeSchedule
from pathfinding_service.typing import AddressReachabilityProtocol
from raiden.messages.path_finding_service import PFSCapacityUpdate, PFSFeeUpdate
from raiden.network.transport.matrix import UserPresence
from raiden.network.transport.matrix.utils import AddressReachability
from raiden.tests.utils.mediation_fees import get_amount_with_fees
from raiden.utils.typing import (
    Address,
    Balance,
    BlockTimeout,
    ChannelID,
    FeeAmount,
    PaymentAmount,
    PaymentWithFeeAmount,
    PeerCapabilities,
    TokenAmount,
    TokenNetworkAddress,
)

log = structlog.get_logger(__name__)


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


def prune_graph(graph: DiGraph, reachability_state: AddressReachabilityProtocol) -> DiGraph:
    """Prunes the given `graph` of all channels where the participants are not  reachable."""
    pruned_graph = DiGraph()
    for p1, p2 in graph.edges:
        nodes_online = (
            reachability_state.get_address_reachability(p1) == AddressReachability.REACHABLE
            and reachability_state.get_address_reachability(p2) == AddressReachability.REACHABLE
        )
        if nodes_online:
            pruned_graph.add_edge(p1, p2, view=graph[p1][p2]["view"])
            pruned_graph.add_edge(p2, p1, view=graph[p2][p1]["view"])

    return pruned_graph


class Path:
    def __init__(
        self,
        G: DiGraph,
        nodes: List[Address],
        value: PaymentAmount,
        reachability_state: AddressReachabilityProtocol,
    ):
        self.G = G
        self.nodes = nodes
        self.value = value
        self.reachability_state = reachability_state
        self.fees = self._check_validity_and_calculate_fees()
        self.metadata = self._get_address_metadata() if self.fees is not None else None
        self.is_valid = self.fees is not None and self.metadata is not None
        log.debug("Created Path object", nodes=nodes, is_valid=self.is_valid, fees=self.fees)

    def _calculate_fees(self) -> Optional[List[FeeAmount]]:
        """Calcluates fees backwards for this path.

        Returns ``None``, if the fee calculation cannot be done.
        """
        total = PaymentWithFeeAmount(self.value)
        fees: List[FeeAmount] = []
        for prev_node, mediator, next_node in reversed(list(window(self.nodes, 3))):
            view_in: ChannelView = self.G[prev_node][mediator]["view"]
            view_out: ChannelView = self.G[mediator][next_node]["view"]

            log.debug(
                "Fee calculation",
                amount=total,
                view_out=view_out,
                view_in=view_in,
                amount_without_fees=total,
                balance_in=view_in.capacity_partner,
                balance_out=view_out.capacity,
                schedule_in=view_in.fee_schedule_receiver,
                schedule_out=view_out.fee_schedule_sender,
                receivable_amount=view_in.capacity,
            )

            amount_with_fees = get_amount_with_fees(
                amount_without_fees=total,
                balance_in=Balance(view_in.capacity_partner),
                balance_out=Balance(view_out.capacity),
                schedule_in=view_in.fee_schedule_receiver,
                schedule_out=view_out.fee_schedule_sender,
                receivable_amount=view_in.capacity,
            )

            if amount_with_fees is None:
                log.warning(
                    "Invalid path because of invalid fee calculation",
                    amount=total,
                    view_out=view_out,
                    view_in=view_in,
                    amount_without_fees=total,
                    balance_in=view_in.capacity_partner,
                    balance_out=view_out.capacity,
                    schedule_in=view_in.fee_schedule_receiver,
                    schedule_out=view_out.fee_schedule_sender,
                    receivable_amount=view_in.capacity,
                )
                return None

            fee = PaymentWithFeeAmount(amount_with_fees - total)
            total += fee  # type: ignore

            fees.append(FeeAmount(fee))

        # The hop to the target does not incur mediation fees
        fees.append(FeeAmount(0))

        return fees

    def _get_address_metadata(
        self,
    ) -> Optional[Dict[str, Dict[str, Union[str, PeerCapabilities]]]]:
        # Check node reachabilities
        metadata: Dict[str, Dict[str, Union[str, PeerCapabilities]]] = {}
        for node in self.nodes:
            node_user_ids = self.reachability_state.get_userids_for_address(node)
            checksummed_address = to_checksum_address(node)
            for user_id in node_user_ids:
                if self.reachability_state.get_userid_presence(user_id) in [
                    UserPresence.ONLINE,
                    UserPresence.UNAVAILABLE,
                ]:
                    displayname = (
                        self.reachability_state._displayname_cache.userid_to_displayname.get(
                            user_id, None
                        )
                    )
                    capabilities = self.reachability_state.get_address_capabilities(node)
                    metadata[checksummed_address] = {
                        "user_id": user_id,
                        "capabilities": capabilities,
                        "displayname": displayname,
                    }
                    # if a reachable user is found we arbitrarily choose
                    # this user for the given address. There should not be another user online
                    break

            if checksummed_address not in metadata:
                log.debug(
                    "Path invalid because of unavailable node",
                    node=node,
                    node_reachability=self.reachability_state.get_address_reachability(node),
                )
                return None

        return metadata

    def _check_validity_and_calculate_fees(self) -> Optional[List[FeeAmount]]:
        """Checks validity of this path and calculates fees if valid.

        Capacity: The capacity for the last channel must be at least
        the payment value. The previous channel's capacity has to be larger
        than value + last channel's capacity, etc.

        Settle timeout: The raiden client will not forward payments if the
        channel over which they receive has a too low settle_timeout. So we
        should not use such routes. See
        https://github.com/raiden-network/raiden-services/issues/5.
        """
        log.debug("Checking path validity", nodes=self.nodes, value=self.value)

        required_capacity = self.value
        edges = reversed(list(self.edge_attrs))
        for edge in edges:
            # Check basic capacity without fees
            if edge["view"].capacity < required_capacity:
                log.debug(
                    "Path invalid because of missing capacity (without fees)",
                    edge=edge,
                    available_capacity=edge["view"].capacity,
                    required_capacity=required_capacity,
                )
                return None

            # Check if settle_timeout / reveal_timeout >= default ratio
            ratio = edge["view"].settle_timeout / edge["view"].reveal_timeout
            if ratio < DEFAULT_SETTLE_TO_REVEAL_TIMEOUT_RATIO:
                log.debug(
                    "Path invalid because of too low reveal timeout ratio",
                    edge=edge,
                    settle_timeout=edge["view"].settle_timeout,
                    reveal_timeout=edge["view"].reveal_timeout,
                    ratio=ratio,
                    required_ratio=DEFAULT_SETTLE_TO_REVEAL_TIMEOUT_RATIO,
                )
                return None

        # Calculate fees
        # This implicitely checks that the channels have sufficient capacity
        return self._calculate_fees()

    @property
    def edge_attrs(self) -> Iterable[dict]:
        return (self.G[node1][node2] for node1, node2 in zip(self.nodes[:-1], self.nodes[1:]))

    @property
    def estimated_fee(self) -> FeeAmount:
        if self.fees:
            return FeeAmount(sum(self.fees))

        return FeeAmount(0)

    def to_dict(self) -> dict:
        assert self.is_valid
        try:
            return dict(
                path=[to_checksum_address(node) for node in self.nodes],
                address_metadata=self.metadata,
                estimated_fee=self.estimated_fee,
            )
        except KeyError:
            raise InconsistentInternalState()


class TokenNetwork:
    """Manages a token network for pathfinding."""

    def __init__(self, token_network_address: TokenNetworkAddress):
        """Initializes a new TokenNetwork."""

        self.address = token_network_address
        self.channel_id_to_addresses: Dict[ChannelID, Tuple[Address, Address]] = dict()
        self.G = DiGraph()

    def __repr__(self) -> str:
        return (
            f"<TokenNetwork address = {to_checksum_address(self.address)} "
            f"num_channels = {len(self.channel_id_to_addresses)}>"
        )

    def handle_channel_opened_event(
        self,
        channel_identifier: ChannelID,
        participant1: Address,
        participant2: Address,
        settle_timeout: BlockTimeout,
    ) -> Channel:
        """Register the channel in the graph, add participants to graph if necessary.

        Corresponds to the ChannelOpened event.
        We swap participants unless participant1 < participant2.
        """

        if participant1 > participant2:
            (participant1, participant2) = (participant2, participant1)

        channel = Channel(
            token_network_address=self.address,
            channel_id=channel_identifier,
            participant1=participant1,
            participant2=participant2,
            settle_timeout=settle_timeout,
        )

        for cv in channel.views:
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
        """Close a channel. This doesn't mean that the channel is settled yet, but it cannot
        transfer any more.

        Corresponds to the ChannelClosed event."""

        # we need to unregister the channel_id here
        participant1, participant2 = self.channel_id_to_addresses.pop(channel_identifier)

        self.G.remove_edge(participant1, participant2)
        self.G.remove_edge(participant2, participant1)

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
        """Sends Capacity Update to PFS including the reveal timeout"""
        (channel_view_to_partner, channel_view_from_partner) = self.get_channel_views_for_partner(
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
        log.debug(
            "Setting capacity",
            updating_participant=message.updating_capacity,
            other_capacity_partner=other_capacity_partner,
            other_capacity=message.other_capacity,
            updating_capacity_partner=updating_capacity_partner,
            result=channel_view_to_partner.channel,
        )
        return channel_view_to_partner.channel

    def handle_channel_fee_update(self, message: PFSFeeUpdate) -> Channel:
        if message.timestamp > datetime.utcnow() + timedelta(hours=1):
            # We don't really care about the time, but if we accept a time far
            # in the future, the client will have problems sending fee updates
            # with increasing time after fixing his clock.
            raise InvalidFeeUpdate("Timestamp is in the future")
        channel_id = message.canonical_identifier.channel_identifier
        participants = self.channel_id_to_addresses[channel_id]
        other_participant = (set(participants) - {message.updating_participant}).pop()
        (channel_view_to_partner, channel_view_from_partner) = self.get_channel_views_for_partner(
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

        # Enable fee apping for both fee schedules
        schedule_in = copy(view.fee_schedule_receiver)
        schedule_in.cap_fees = True
        schedule_out = copy(view.fee_schedule_sender)
        schedule_out.cap_fees = True

        amount_with_fees = get_amount_with_fees(
            amount_without_fees=PaymentWithFeeAmount(amount),
            balance_in=Balance(view.capacity),
            balance_out=Balance(view.capacity),
            schedule_in=schedule_in,
            schedule_out=schedule_out,
            receivable_amount=view.capacity,
        )

        if amount_with_fees is None:
            return float("inf")

        fee = FeeAmount(amount_with_fees - amount)
        fee_weight = fee / 1e18 * fee_penalty

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
        reachability_state: AddressReachabilityProtocol,
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
                for p in (Path(self.G, nodes, value, reachability_state) for nodes in all_paths)
                if p.is_valid and p.nodes not in disallowed_paths
            )
            return path
        except StopIteration:
            return None

    def check_path_request_errors(
        self,
        source: Address,
        target: Address,
        value: PaymentAmount,
        reachability_state: AddressReachabilityProtocol,
    ) -> Optional[str]:
        """Checks for basic problems with the path requests. Returns error message or `None`"""

        if reachability_state.get_address_reachability(source) != AddressReachability.REACHABLE:
            return "Source not online"

        if reachability_state.get_address_reachability(target) != AddressReachability.REACHABLE:
            return "Target not online"

        if not any(self.G.edges(source)):
            return "No channel from source"
        if not any(self.G.edges(target)):
            return "No channel to target"

        source_capacities = [view.capacity for _, _, view in self.G.out_edges(source, data="view")]
        if max(source_capacities) < value:
            debug_capacities = [
                (to_checksum_address(a), to_checksum_address(b), view.capacity)
                for a, b, view in self.G.out_edges(source, data="view")
            ]
            log.debug("Insufficient capacities", capacities=debug_capacities)
            message = (
                f"Source does not have a channel with sufficient capacity "
                f"(current capacities: {source_capacities} < requested amount: "
                f" {value})"
            )
            return message
        target_capacities = [view.capacity for _, _, view in self.G.in_edges(target, data="view")]
        if max(target_capacities) < value:
            return "Target does not have a channel with sufficient capacity (%s < %s)" % (
                target_capacities,
                value,
            )

        try:
            next(nx.shortest_simple_paths(G=self.G, source=source, target=target))
        except NetworkXNoPath:
            return "No route from source to target"

        return None

    def get_paths(  # pylint: disable=too-many-arguments, too-many-locals
        self,
        source: Address,
        target: Address,
        value: PaymentAmount,
        max_paths: int,
        reachability_state: AddressReachabilityProtocol,
        diversity_penalty: float = DIVERSITY_PEN_DEFAULT,
        fee_penalty: float = FEE_PEN_DEFAULT,
    ) -> List[Path]:
        """Find best routes according to given preferences

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
        )

        # TODO: improve the pruning
        # Currently we make a snapshot of the currently reachable nodes, so the searched graph
        # becomes smaller
        pruned_graph = prune_graph(graph=self.G, reachability_state=reachability_state)

        while len(paths) < max_paths:
            try:
                path = self._get_single_path(
                    graph=pruned_graph,
                    source=source,
                    target=target,
                    value=value,
                    reachability_state=reachability_state,
                    visited=visited,
                    disallowed_paths=[p.nodes for p in paths],
                    fee_penalty=fee_penalty,
                )
            except (NetworkXNoPath, NodeNotFound):
                log.info(
                    "Found no path for payment in pruned graph",
                    source=source,
                    target=target,
                    value=value,
                    max_paths=max_paths,
                    diversity_penalty=diversity_penalty,
                    fee_penalty=fee_penalty,
                    reachabilities=reachability_state,
                )
                return []

            if path is None:
                break
            paths.append(path)

            # update visited penalty dict
            for edge in path.edge_attrs:
                channel_id = edge["view"].channel_id
                visited[channel_id] += diversity_penalty

        log.info(
            "Returning paths for payment",
            source=source,
            target=target,
            value=value,
            max_paths=max_paths,
            diversity_penalty=diversity_penalty,
            fee_penalty=fee_penalty,
            paths=paths,
        )
        return paths

    def suggest_partner(
        self, reachability_state: AddressReachabilityProtocol, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Suggest good partners for Raiden nodes joining the token network"""

        # centrality
        centrality_of_node = nx.algorithms.centrality.closeness_centrality(self.G)

        # uptime, only include online nodes
        uptime_of_node = {}
        now = datetime.utcnow()
        for node in self.G.nodes:
            node_reach_state = reachability_state.get_address_reachability_state(node)
            if node_reach_state.reachability == AddressReachability.REACHABLE:
                uptime_of_node[node] = (now - node_reach_state.time).total_seconds()

        # capacity
        capacity_of_node = {}
        for node in uptime_of_node:
            channel_views = [
                channel_data["view"] for _, _, channel_data in self.G.edges(node, data=True)
            ]
            capacity_of_node[node] = sum(cv.capacity for cv in channel_views)

        # sort by overall score
        suggestions = [
            dict(
                address=to_checksum_address(node),
                score=centrality_of_node[node] * uptime * capacity_of_node[node],
                centrality=centrality_of_node[node],
                uptime=uptime,
                capacity=capacity_of_node[node],
            )
            for node, uptime in uptime_of_node.items()
        ]
        return sorted(suggestions, key=lambda n: -n["score"])[:limit]

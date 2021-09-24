# pylint: disable=redefined-outer-name
import random
from typing import Callable, Generator, List
from unittest.mock import Mock, patch

import pytest
from eth_utils import decode_hex, to_canonical_address
from web3 import Web3
from web3.contract import Contract

from pathfinding_service.model.token_network import TokenNetwork
from pathfinding_service.service import PathfindingService
from raiden.constants import EMPTY_SIGNATURE
from raiden.messages.path_finding_service import PFSCapacityUpdate
from raiden.network.transport.matrix import AddressReachability
from raiden.transfer.identifiers import CanonicalIdentifier
from raiden.utils.typing import (
    Address,
    BlockNumber,
    BlockTimeout,
    ChainID,
    ChannelID,
    Nonce,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.utils import private_key_to_address
from src.utils import to_checksum_address

from ...libs.mocks.web3 import Web3Mock
from ..utils import SimpleReachabilityContainer


@pytest.fixture(scope="session")
def channel_descriptions_case_1() -> List:
    """Creates a network with some edge cases.

    These include disconneced subgraph, depleted channels...
    """

    # Now initialize some channels in this network.
    # The tuples in channel_descriptions define the following:
    # (
    #     p1_index,
    #     p1_capacity,
    #     p1_fee,
    #     p1_reveal_timeout,
    #     p1_reachability,
    #     p2_index,
    #     p2_capacity,
    #     p2_fee,
    #     p2_reveal_timeout,
    #     p2_reachability,
    #     settle_timeout
    # )
    # Topology:
    #       /-------------\
    # 0 -- 1 -- 2 -- 3 -- 4    5 -- 6
    #  \-------/

    reach = AddressReachability.REACHABLE

    channel_descriptions = [
        (0, 90, 10, 2, reach, 1, 60, 15, 2, reach, 14),  # capacities  90 --  60
        (1, 130, 8, 2, reach, 2, 40, 12, 2, reach, 14),  # capacities 130 --  40
        (2, 80, 7, 2, reach, 3, 20, 10, 2, reach, 3),  # capacities  80 --  20
        (3, 50, 11, 2, reach, 4, 50, 11, 2, reach, 14),  # capacities  50 --  50
        (0, 0, 15, 2, reach, 2, 120, 25, 2, reach, 14),  # capacities   0 -- 120
        (1, 35, 100, 2, reach, 4, 35, 18, 2, reach, 14),  # capacities  35 --  35
        (5, 550, 30, 2, reach, 6, 700, 40, 2, reach, 14),  # capacities 550 -- 700
    ]
    return channel_descriptions


@pytest.fixture
def channel_descriptions_case_2() -> List:
    """Creates a network with three paths from 0 to 4.

    The paths differ in length and cost.
    """

    # Now initialize some channels in this network.
    # The tuples in channel_descriptions define the following:
    # (
    #     p1_index,
    #     p1_capacity,
    #     p1_fee,
    #     p1_reveal_timeout,
    #     p1_reachability,
    #     p2_index,
    #     p2_capacity,
    #     p2_fee,
    #     p2_reveal_timeout,
    #     p2_reachability,
    #     settle_timeout
    # )
    # Topology:
    #  /----- 1 ----\
    # 0 -- 2 -- 3 -- 4
    #       \-- 5 --/

    reach = AddressReachability.REACHABLE

    channel_descriptions = [
        (0, 90, 3000, 2, reach, 1, 60, 3000, 2, reach, 15),  # capacities  90 --  60
        (1, 130, 2000, 2, reach, 4, 40, 2000, 2, reach, 15),  # capacities 130 --  40
        (0, 80, 1000, 2, reach, 2, 10, 1000, 2, reach, 15),  # capacities  80 --  10
        (2, 50, 1500, 2, reach, 3, 50, 1500, 2, reach, 15),  # capacities  50 --  50
        (3, 60, 1000, 2, reach, 4, 120, 1000, 2, reach, 15),  # capacities  60 -- 120
        (2, 35, 1000, 2, reach, 5, 35, 1000, 2, reach, 15),  # capacities  35 --  35
        (5, 550, 1000, 2, reach, 4, 700, 1000, 2, reach, 15),  # capacities 550 -- 700
    ]
    return channel_descriptions


@pytest.fixture
def channel_descriptions_case_3() -> List:
    """Creates a network partly overlapping paths from 0 to 8"""

    # Now initialize some channels in this network.
    # The tuples in channel_descriptions define the following:
    # (
    #     p1_index,
    #     p1_capacity,
    #     p1_fee,
    #     p1_reveal_timeout,
    #     p1_reachability,
    #     p2_index,
    #     p2_capacity,
    #     p2_fee,
    #     p2_reveal_timeout,
    #     p2_reachability,
    #     settle_timeout
    # )
    # Topology:
    #    /- 1 - 2 - 3 - 4 --\
    #   /          /-- 5 -\ |
    #  /      /--- 6 ---\ / |
    # 0----- 7 --------- 8 -/
    #         \- 9 - 10 -/

    reach = AddressReachability.REACHABLE

    channel_descriptions = [
        (a, 100, 0, 2, reach, b, 100, 0, 2, reach, 15)
        for a, b in [
            (0, 1),
            (1, 2),
            (2, 3),
            (3, 4),
            (4, 8),
            (0, 7),
            (7, 6),
            (7, 8),
            (7, 9),
            (9, 10),
            (10, 8),
            (5, 8),
            (6, 5),
            (6, 8),
        ]
    ]
    return channel_descriptions


@pytest.fixture(scope="session")
def populate_token_network() -> Callable:
    # pylint: disable=too-many-locals
    def populate_token_network(
        token_network: TokenNetwork,
        reachability_state: SimpleReachabilityContainer,
        addresses: List[Address],
        channel_descriptions: List,
    ):
        for (
            channel_id,
            (
                p1_index,
                p1_capacity,
                _p1_fee,
                p1_reveal_timeout,
                p1_reachability,
                p2_index,
                p2_capacity,
                _p2_fee,
                p2_reveal_timeout,
                p2_reachability,
                settle_timeout,
            ),
        ) in enumerate(channel_descriptions):
            participant1 = addresses[p1_index]
            participant2 = addresses[p2_index]
            token_network.handle_channel_opened_event(
                channel_identifier=ChannelID(channel_id),
                participant1=participant1,
                participant2=participant2,
                settle_timeout=settle_timeout,
            )

            token_network.handle_channel_balance_update_message(
                PFSCapacityUpdate(
                    canonical_identifier=CanonicalIdentifier(
                        chain_identifier=ChainID(61),
                        channel_identifier=ChannelID(channel_id),
                        token_network_address=TokenNetworkAddress(token_network.address),
                    ),
                    updating_participant=addresses[p1_index],
                    other_participant=addresses[p2_index],
                    updating_nonce=Nonce(1),
                    other_nonce=Nonce(1),
                    updating_capacity=p1_capacity,
                    other_capacity=p2_capacity,
                    reveal_timeout=p1_reveal_timeout,
                    signature=EMPTY_SIGNATURE,
                ),
                updating_capacity_partner=TokenAmount(0),
                other_capacity_partner=TokenAmount(0),
            )
            token_network.handle_channel_balance_update_message(
                PFSCapacityUpdate(
                    canonical_identifier=CanonicalIdentifier(
                        chain_identifier=ChainID(61),
                        channel_identifier=ChannelID(channel_id),
                        token_network_address=TokenNetworkAddress(token_network.address),
                    ),
                    updating_participant=addresses[p2_index],
                    other_participant=addresses[p1_index],
                    updating_nonce=Nonce(2),
                    other_nonce=Nonce(1),
                    updating_capacity=p2_capacity,
                    other_capacity=p1_capacity,
                    reveal_timeout=p2_reveal_timeout,
                    signature=EMPTY_SIGNATURE,
                ),
                updating_capacity_partner=TokenAmount(p1_capacity),
                other_capacity_partner=TokenAmount(p2_capacity),
            )

            # Update presence state according to scenario
            reachability_state.reachabilities[participant1] = p1_reachability
            reachability_state.reachabilities[participant2] = p2_reachability

    return populate_token_network


@pytest.fixture
def populate_token_network_case_1(
    populate_token_network: Callable,
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
    channel_descriptions_case_1: List,
):
    populate_token_network(
        token_network_model, reachability_state, addresses, channel_descriptions_case_1
    )


@pytest.fixture
def populate_token_network_case_2(
    populate_token_network: Callable,
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
    channel_descriptions_case_2: List,
):
    populate_token_network(
        token_network_model, reachability_state, addresses, channel_descriptions_case_2
    )


@pytest.fixture
def populate_token_network_case_3(
    populate_token_network: Callable,
    token_network_model: TokenNetwork,
    reachability_state: SimpleReachabilityContainer,
    addresses: List[Address],
    channel_descriptions_case_3: List,
):
    populate_token_network(
        token_network_model, reachability_state, addresses, channel_descriptions_case_3
    )


@pytest.fixture
def pathfinding_service_mock_empty() -> Generator[PathfindingService, None, None]:
    with patch("pathfinding_service.service.MatrixListener", new=Mock):
        web3_mock = Web3Mock()

        mock_udc = Mock(address=bytes([8] * 20))
        mock_udc.functions.effectiveBalance.return_value.call.return_value = 10000
        mock_udc.functions.token.return_value.call.return_value = to_checksum_address(
            bytes([7] * 20)
        )
        pathfinding_service = PathfindingService(
            web3=web3_mock,
            contracts={
                CONTRACT_TOKEN_NETWORK_REGISTRY: Mock(address=bytes([9] * 20)),
                CONTRACT_USER_DEPOSIT: mock_udc,
            },
            sync_start_block=BlockNumber(0),
            required_confirmations=BlockTimeout(0),
            poll_interval=0,
            private_key=PrivateKey(
                decode_hex("3a1076bf45ab87712ad64ccb3b10217737f7faacbf2872e88fdd9a537d8fe266")
            ),
            db_filename=":memory:",
        )

        yield pathfinding_service
        pathfinding_service.stop()


@pytest.fixture
def pathfinding_service_mock(
    token_network_model: TokenNetwork, pathfinding_service_mock_empty: PathfindingService
) -> Generator[PathfindingService, None, None]:

    pathfinding_service_mock_empty.token_networks = {
        token_network_model.address: token_network_model
    }
    pathfinding_service_mock_empty.database.upsert_token_network(token_network_model.address)
    pathfinding_service_mock_empty.matrix_listener.base_url = "https://matrix.server"

    yield pathfinding_service_mock_empty


@pytest.fixture
def pathfinding_service_web3_mock(
    web3: Web3,
    user_deposit_contract: Contract,
    get_private_key: Callable,
    create_service_account: Callable,
) -> Generator[PathfindingService, None, None]:
    pfs_address = to_canonical_address(create_service_account())
    with patch("pathfinding_service.service.MatrixListener", new=Mock):
        pathfinding_service = PathfindingService(
            web3=web3,
            contracts={
                CONTRACT_TOKEN_NETWORK_REGISTRY: Mock(address="0x" + "9" * 40),
                CONTRACT_USER_DEPOSIT: user_deposit_contract,
            },
            sync_start_block=BlockNumber(0),
            required_confirmations=BlockTimeout(1),
            poll_interval=0,
            private_key=get_private_key(pfs_address),
            db_filename=":memory:",
        )

        yield pathfinding_service


@pytest.fixture
def populate_token_network_random(
    token_network_model: TokenNetwork, private_keys: List[str]
) -> None:
    number_of_channels = 300
    # seed for pseudo-randomness from config constant, that changes from time to time
    random.seed(number_of_channels)

    for channel_id_int in range(number_of_channels):
        channel_id = ChannelID(channel_id_int)

        private_key1, private_key2 = random.sample(private_keys, 2)
        address1 = private_key_to_address(private_key1)
        address2 = private_key_to_address(private_key2)
        settle_timeout = BlockTimeout(15)
        token_network_model.handle_channel_opened_event(
            channel_identifier=channel_id,
            participant1=address1,
            participant2=address2,
            settle_timeout=settle_timeout,
        )

        # deposit to channels
        deposit1 = TokenAmount(random.randint(0, 1000))
        deposit2 = TokenAmount(random.randint(0, 1000))
        address1, address2 = token_network_model.channel_id_to_addresses[channel_id]
        token_network_model.handle_channel_balance_update_message(
            PFSCapacityUpdate(
                canonical_identifier=CanonicalIdentifier(
                    chain_identifier=ChainID(61),
                    channel_identifier=channel_id,
                    token_network_address=TokenNetworkAddress(token_network_model.address),
                ),
                updating_participant=address1,
                other_participant=address2,
                updating_nonce=Nonce(1),
                other_nonce=Nonce(1),
                updating_capacity=deposit1,
                other_capacity=deposit2,
                reveal_timeout=BlockTimeout(2),
                signature=EMPTY_SIGNATURE,
            ),
            updating_capacity_partner=TokenAmount(0),
            other_capacity_partner=TokenAmount(0),
        )
        token_network_model.handle_channel_balance_update_message(
            PFSCapacityUpdate(
                canonical_identifier=CanonicalIdentifier(
                    chain_identifier=ChainID(61),
                    channel_identifier=channel_id,
                    token_network_address=TokenNetworkAddress(token_network_model.address),
                ),
                updating_participant=address2,
                other_participant=address1,
                updating_nonce=Nonce(2),
                other_nonce=Nonce(1),
                updating_capacity=deposit2,
                other_capacity=deposit1,
                reveal_timeout=BlockTimeout(2),
                signature=EMPTY_SIGNATURE,
            ),
            updating_capacity_partner=TokenAmount(deposit1),
            other_capacity_partner=TokenAmount(deposit2),
        )

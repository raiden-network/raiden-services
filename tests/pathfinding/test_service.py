import os
from typing import List
from unittest.mock import Mock, patch

from pathfinding_service.service import PathfindingService
from raiden.utils.typing import BlockNumber, ChannelID
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT
from raiden_contracts.tests.utils import get_random_privkey
from raiden_libs.events import (
    ReceiveChannelOpenedEvent,
    ReceiveTokenNetworkCreatedEvent,
    UpdatedHeadBlockEvent,
)
from raiden_libs.types import Address, TokenNetworkAddress

from ..libs.mocks.web3 import ContractMock, Web3Mock


def test_save_and_load_token_networks(pathfinding_service_mock):
    pfs = pathfinding_service_mock
    pfs.token_networks = {}  # the mock does not fit this case exactly

    token_address = Address("0x" + "1" * 40)
    token_network_address = TokenNetworkAddress("0x" + "2" * 40)
    channel_id = ChannelID(1)
    p1 = Address("0x" + "3" * 40)
    p2 = Address("0x" + "4" * 40)
    events = [
        ReceiveTokenNetworkCreatedEvent(
            token_address=token_address,
            token_network_address=token_network_address,
            block_number=BlockNumber(1),
        ),
        ReceiveChannelOpenedEvent(
            token_network_address=token_network_address,
            channel_identifier=channel_id,
            participant1=p1,
            participant2=p2,
            settle_timeout=2 ** 65,  # larger than max_uint64 to check hex storage
            block_number=BlockNumber(2),
        ),
    ]
    for event in events:
        pfs.handle_event(event)
    assert len(pfs.token_networks) == 1

    loaded_networks = pfs._load_token_networks()
    assert len(loaded_networks) == 1

    orig = list(pfs.token_networks.values())[0]
    loaded = list(loaded_networks.values())[0]
    assert loaded.address == orig.address
    assert loaded.channel_id_to_addresses == orig.channel_id_to_addresses
    assert loaded.G.nodes == orig.G.nodes


@patch("pathfinding_service.service.MatrixListener", Mock)
def test_crash(tmpdir, mockchain):
    """ Process blocks and compare results with/without crash

    A somewhat meaninful crash handling is simulated by not including the
    UpdatedHeadBlockEvent in every block.
    """
    token_address = Address("0x" + "1" * 40)
    token_network_address = TokenNetworkAddress("0x" + "2" * 40)
    channel_id = ChannelID(1)
    p1 = Address("0x" + "3" * 40)
    p2 = Address("0x" + "4" * 40)
    events = [
        [
            ReceiveTokenNetworkCreatedEvent(
                token_address=token_address,
                token_network_address=token_network_address,
                block_number=BlockNumber(1),
            )
        ],
        [UpdatedHeadBlockEvent(BlockNumber(2))],
        [
            ReceiveChannelOpenedEvent(
                token_network_address=token_network_address,
                channel_identifier=channel_id,
                participant1=p1,
                participant2=p2,
                settle_timeout=1000,
                block_number=BlockNumber(3),
            )
        ],
        [UpdatedHeadBlockEvent(BlockNumber(4))],
    ]
    mockchain(events)

    server_private_key = get_random_privkey()
    contracts = {
        CONTRACT_TOKEN_NETWORK_REGISTRY: ContractMock(),
        CONTRACT_USER_DEPOSIT: ContractMock(),
    }

    def new_service(filename):
        service = PathfindingService(
            web3=Web3Mock(),
            private_key=server_private_key,
            contracts=contracts,
            db_filename=os.path.join(tmpdir, filename),
        )
        return service

    # initialize both services
    stable_service = new_service("stable.db")
    crashy_service = new_service("crashy.db")

    # process each block and compare results between crashy and stable service
    for to_block in range(len(events)):
        crashy_service = new_service("crashy.db")  # new instance to simulate crash
        result_state: List[dict] = []
        for service in [stable_service, crashy_service]:
            service._process_new_blocks(to_block)
            result_state.append(dict(db_dump=list(service.database.conn.iterdump())))

        # both instances should have the same state after processing
        for stable_state, crashy_state in zip(result_state[0].values(), result_state[1].values()):
            # do asserts for each key separately to get better error messages
            assert stable_state == crashy_state

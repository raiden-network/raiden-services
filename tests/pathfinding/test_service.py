import os
from datetime import datetime
from typing import List
from unittest.mock import Mock, call, patch

import pytest
from eth_utils import to_checksum_address

from pathfinding_service.model.token_network import PFSFeeUpdate
from pathfinding_service.service import PathfindingService
from raiden.constants import EMPTY_SIGNATURE
from raiden.messages.synchronization import Processed
from raiden.tests.utils.factories import make_privkey_address, make_token_network_address
from raiden.transfer.identifiers import CanonicalIdentifier
from raiden.transfer.mediated_transfer.mediation_fee import FeeScheduleState
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import (
    Address,
    BlockNumber,
    BlockTimeout,
    ChainID,
    ChannelID,
    FeeAmount,
    MessageID,
    ProportionalFeeAmount,
    TokenAmount,
    TokenNetworkAddress,
)
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK_REGISTRY, CONTRACT_USER_DEPOSIT
from raiden_contracts.tests.utils import get_random_privkey
from raiden_libs.events import (
    ReceiveChannelClosedEvent,
    ReceiveChannelOpenedEvent,
    ReceiveTokenNetworkCreatedEvent,
    UpdatedHeadBlockEvent,
)
from raiden_libs.logging import format_to_hex
from raiden_libs.states import BlockchainState

from ..libs.mocks.web3 import ContractMock, Web3Mock

PARTICIPANT1_PRIVKEY, PARTICIPANT1 = make_privkey_address()
PARTICIPANT2 = Address(bytes([2] * 20))


def test_save_and_load_token_networks(pathfinding_service_mock_empty):
    pfs = pathfinding_service_mock_empty

    token_address = Address(bytes([1] * 20))
    token_network_address = TokenNetworkAddress(bytes([2] * 20))
    channel_id = ChannelID(1)
    p1 = Address(bytes([3] * 20))
    p2 = Address(bytes([4] * 20))
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
            settle_timeout=BlockTimeout(2 ** 65),  # larger than max_uint64 to check hex storage
            block_number=BlockNumber(2),
        ),
    ]
    for event in events:
        pfs.handle_event(event)
    assert len(pfs.token_networks) == 1

    loaded_networks = pfs._load_token_networks()  # pylint: disable=protected-access
    assert len(loaded_networks) == 1

    orig = list(pfs.token_networks.values())[0]
    loaded = list(loaded_networks.values())[0]
    assert loaded.address == orig.address
    assert loaded.channel_id_to_addresses == orig.channel_id_to_addresses
    assert loaded.G.nodes == orig.G.nodes


@patch("pathfinding_service.service.MatrixListener", Mock)
def test_crash(tmpdir, mockchain):  # pylint: disable=too-many-locals
    """ Process blocks and compare results with/without crash

    A somewhat meaninful crash handling is simulated by not including the
    UpdatedHeadBlockEvent in every block.
    """
    token_address = Address(bytes([1] * 20))
    token_network_address = TokenNetworkAddress(bytes([2] * 20))
    channel_id = ChannelID(1)
    p1 = Address(bytes([3] * 20))
    p2 = Address(bytes([4] * 20))
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
                settle_timeout=BlockTimeout(1000),
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
            contracts=contracts,  # type: ignore
            sync_start_block=BlockNumber(0),
            required_confirmations=BlockTimeout(0),
            poll_interval=0,
            db_filename=os.path.join(tmpdir, filename),
        )
        return service

    # initialize stable service
    stable_service = new_service("stable.db")

    # process each block and compare results between crashy and stable service
    for to_block in range(len(events)):
        crashy_service = new_service("crashy.db")  # new instance to simulate crash
        result_state: List[dict] = []
        for service in [stable_service, crashy_service]:
            service._process_new_blocks(BlockNumber(to_block))  # pylint: disable=protected-access
            result_state.append(dict(db_dump=list(service.database.conn.iterdump())))

        # both instances should have the same state after processing
        for stable_state, crashy_state in zip(result_state[0].values(), result_state[1].values()):
            if isinstance(stable_state, BlockchainState):
                assert stable_state.chain_id == crashy_state.chain_id
                assert (
                    stable_state.token_network_registry_address
                    == crashy_state.token_network_registry_address
                )
                assert stable_state.latest_committed_block == crashy_state.latest_committed_block
                assert (
                    stable_state.monitor_contract_address == crashy_state.monitor_contract_address
                )
                assert stable_state.token_network_addresses == crashy_state.token_network_addresses
                # Do not compare `current_event_filter_interval`, this is allowed to be different
            else:
                assert stable_state == crashy_state

        crashy_service.database.conn.close()  # close the db connection so we can access it again


def test_token_network_created(pathfinding_service_mock):
    token_address = Address(bytes([1] * 20))
    token_network_address = TokenNetworkAddress(bytes(bytes([2] * 20)))
    network_event = ReceiveTokenNetworkCreatedEvent(
        token_address=token_address,
        token_network_address=token_network_address,
        block_number=BlockNumber(1),
    )

    assert not pathfinding_service_mock.follows_token_network(token_network_address)
    assert len(pathfinding_service_mock.token_networks) == 1

    pathfinding_service_mock.handle_event(network_event)
    assert pathfinding_service_mock.follows_token_network(token_network_address)
    assert len(pathfinding_service_mock.token_networks) == 2

    # Test idempotency
    pathfinding_service_mock.handle_event(network_event)
    assert pathfinding_service_mock.follows_token_network(token_network_address)
    assert len(pathfinding_service_mock.token_networks) == 2


def setup_channel(pathfinding_service_mock, token_network_model):
    channel_event = ReceiveChannelOpenedEvent(
        token_network_address=token_network_model.address,
        channel_identifier=ChannelID(1),
        participant1=PARTICIPANT1,
        participant2=PARTICIPANT2,
        settle_timeout=BlockTimeout(20),
        block_number=BlockNumber(1),
    )
    assert len(pathfinding_service_mock.token_networks) == 1
    assert len(token_network_model.channel_id_to_addresses) == 0
    pathfinding_service_mock.handle_event(channel_event)


def test_token_channel_opened(pathfinding_service_mock, token_network_model):
    setup_channel(pathfinding_service_mock, token_network_model)
    assert len(pathfinding_service_mock.token_networks) == 1
    assert len(token_network_model.channel_id_to_addresses) == 1

    # Test invalid token network address
    channel_event = ReceiveChannelOpenedEvent(
        token_network_address=TokenNetworkAddress(bytes([2] * 20)),
        channel_identifier=ChannelID(1),
        participant1=PARTICIPANT1,
        participant2=PARTICIPANT2,
        settle_timeout=BlockTimeout(20),
        block_number=BlockNumber(1),
    )

    pathfinding_service_mock.handle_event(channel_event)
    assert len(pathfinding_service_mock.token_networks) == 1
    assert len(token_network_model.channel_id_to_addresses) == 1

    # Check that presence of these addresses is followed
    pathfinding_service_mock.matrix_listener.follow_address_presence.assert_has_calls(
        [call(PARTICIPANT1, refresh=True), call(PARTICIPANT2, refresh=True)]
    )


def test_token_channel_closed(pathfinding_service_mock, token_network_model):
    setup_channel(pathfinding_service_mock, token_network_model)

    token_network_address = make_token_network_address()

    # Test invalid token network address
    close_event = ReceiveChannelClosedEvent(
        token_network_address=token_network_address,
        channel_identifier=ChannelID(1),
        closing_participant=PARTICIPANT1,
        block_number=BlockNumber(2),
    )

    pathfinding_service_mock.handle_event(close_event)
    assert len(pathfinding_service_mock.token_networks) == 1
    assert len(token_network_model.channel_id_to_addresses) == 1

    # Test proper token network address
    close_event.token_network_address = token_network_model.address

    pathfinding_service_mock.handle_event(close_event)
    assert len(pathfinding_service_mock.token_networks) == 1
    assert len(token_network_model.channel_id_to_addresses) == 0

    # Test non-existent channel
    close_event.channel_identifier = ChannelID(123)

    pathfinding_service_mock.handle_event(close_event)
    assert len(pathfinding_service_mock.token_networks) == 1
    assert len(token_network_model.channel_id_to_addresses) == 0


@pytest.mark.parametrize("order", ["normal", "fee_update_before_channel_open"])
def test_update_fee(order, pathfinding_service_mock, token_network_model):
    pathfinding_service_mock.database.insert(
        "token_network", dict(address=token_network_model.address)
    )
    if order == "normal":
        setup_channel(pathfinding_service_mock, token_network_model)

    fee_schedule = FeeScheduleState(
        flat=FeeAmount(1),
        proportional=ProportionalFeeAmount(int(0.1e9)),
        imbalance_penalty=[(TokenAmount(0), FeeAmount(0)), (TokenAmount(10), FeeAmount(10))],
    )
    fee_update = PFSFeeUpdate(
        canonical_identifier=CanonicalIdentifier(
            chain_identifier=ChainID(61),
            token_network_address=token_network_model.address,
            channel_identifier=ChannelID(1),
        ),
        updating_participant=PARTICIPANT1,
        fee_schedule=fee_schedule,
        timestamp=datetime.utcnow(),
        signature=EMPTY_SIGNATURE,
    )
    fee_update.sign(LocalSigner(PARTICIPANT1_PRIVKEY))
    pathfinding_service_mock.handle_message(fee_update)

    if order == "fee_update_before_channel_open":
        setup_channel(pathfinding_service_mock, token_network_model)

    cv = token_network_model.G[PARTICIPANT1][PARTICIPANT2]["view"]
    for key in ("flat", "proportional", "imbalance_penalty"):
        assert getattr(cv.fee_schedule_sender, key) == getattr(fee_schedule, key)


def test_unhandled_message(pathfinding_service_mock, log):
    unknown_message = Processed(MessageID(123), signature=EMPTY_SIGNATURE)
    unknown_message.sign(LocalSigner(PARTICIPANT1_PRIVKEY))

    pathfinding_service_mock.handle_message(unknown_message)
    assert log.has("Ignoring message", unknown_message=unknown_message)


def test_logging_processor():
    # test if our logging processor changes bytes to checksum addresses
    # even if bytes-addresses are entangled into events
    logger = Mock()
    log_method = Mock()

    address = Address(b"\x7f[\xf6\xc9To\xa8\x185w\xe4\x9f\x15\xbc\xef@mr\xd5\xd9")
    address_log = format_to_hex(
        _logger=logger, _log_method=log_method, event_dict=dict(address=address)
    )
    assert to_checksum_address(address) == address_log["address"]

    address2 = Address(b"\x7f[\xf6\xc9To\xa8\x185w\xe4\x9f\x15\xbc\xef@mr\xd5\xd1")
    event = ReceiveTokenNetworkCreatedEvent(
        token_address=address,
        token_network_address=TokenNetworkAddress(address2),
        block_number=BlockNumber(1),
    )
    event_log = format_to_hex(_logger=logger, _log_method=log_method, event_dict=dict(event=event))
    assert (  # pylint: disable=unsubscriptable-object
        to_checksum_address(address) == event_log["event"]["token_address"]
    )
    assert (  # pylint: disable=unsubscriptable-object
        to_checksum_address(address2) == event_log["event"]["token_network_address"]
    )
    assert (  # pylint: disable=unsubscriptable-object
        event_log["event"]["type_name"] == "ReceiveTokenNetworkCreatedEvent"
    )

    message = PFSFeeUpdate(
        canonical_identifier=CanonicalIdentifier(
            chain_identifier=ChainID(61),
            token_network_address=TokenNetworkAddress(address),
            channel_identifier=ChannelID(1),
        ),
        updating_participant=PARTICIPANT1,
        fee_schedule=FeeScheduleState(),
        timestamp=datetime.utcnow(),
        signature=EMPTY_SIGNATURE,
    )
    message_log = format_to_hex(
        _logger=logger, _log_method=log_method, event_dict=dict(message=message)
    )
    assert (  # pylint: disable=unsubscriptable-object
        to_checksum_address(address)
        == message_log["message"]["canonical_identifier"]["token_network_address"]
    )
    assert (  # pylint: disable=unsubscriptable-object
        message_log["message"]["type_name"] == "PFSFeeUpdate"
    )

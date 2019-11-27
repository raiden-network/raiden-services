import json
from datetime import datetime
from typing import List
from uuid import uuid4

from eth_utils import to_checksum_address

from pathfinding_service.database import PFSDatabase
from pathfinding_service.model.feedback import FeedbackToken
from raiden.constants import EMPTY_SIGNATURE
from raiden.messages.path_finding_service import PFSCapacityUpdate, PFSFeeUpdate
from raiden.tests.utils.factories import make_address, make_privkey_address
from raiden.transfer.identifiers import CanonicalIdentifier
from raiden.transfer.mediated_transfer.mediation_fee import FeeScheduleState
from raiden.utils.signer import LocalSigner
from raiden.utils.typing import (
    Address,
    BlockTimeout,
    ChainID,
    ChannelID,
    Nonce,
    TokenAmount,
    TokenNetworkAddress,
)


def db_has_feedback_for(database: PFSDatabase, token: FeedbackToken, route: List[Address]) -> bool:
    hexed_route = [to_checksum_address(e) for e in route]
    feedback = database.conn.execute(
        """SELECT successful FROM feedback WHERE
            token_id = ? AND
            token_network_address = ? AND
            route = ?;
        """,
        [token.id.hex, to_checksum_address(token.token_network_address), json.dumps(hexed_route)],
    ).fetchone()

    if feedback:
        return feedback["successful"] is not None

    return False


def test_insert_feedback_token(pathfinding_service_mock):
    token_network_address = TokenNetworkAddress(b"1" * 20)
    route = [Address(b"2" * 20), Address(b"3" * 20)]

    token = FeedbackToken(token_network_address=token_network_address)
    database = pathfinding_service_mock.database
    database.prepare_feedback(token=token, route=route)

    # Test round-trip
    stored = database.get_feedback_token(
        token_id=token.id, token_network_address=token_network_address, route=route
    )
    assert stored == token

    # Test different UUID
    stored = database.get_feedback_token(
        token_id=uuid4(), token_network_address=token_network_address, route=route
    )
    assert stored is None

    # Test different token network address
    token_network_address_wrong = TokenNetworkAddress(b"9" * 20)
    stored = database.get_feedback_token(
        token_id=uuid4(), token_network_address=token_network_address_wrong, route=route
    )
    assert stored is None

    # Test different route
    route_wrong = [Address(b"2" * 20), Address(b"3" * 20), Address(b"4" * 20)]
    stored = database.get_feedback_token(
        token_id=uuid4(), token_network_address=token_network_address, route=route_wrong
    )
    assert stored is None

    # Test empty route
    stored = database.get_feedback_token(
        token_id=uuid4(), token_network_address=token_network_address, route=[]
    )
    assert stored is None


def test_feedback(pathfinding_service_mock):
    token_network_address = TokenNetworkAddress(b"1" * 20)
    route = [Address(b"2" * 20), Address(b"3" * 20)]
    other_route = [Address(b"2" * 20), Address(b"4" * 20)]

    token = FeedbackToken(token_network_address=token_network_address)
    other_token = FeedbackToken(token_network_address=token_network_address)

    database = pathfinding_service_mock.database
    assert not db_has_feedback_for(database=database, token=token, route=route)
    assert not db_has_feedback_for(database=database, token=token, route=other_route)
    assert not db_has_feedback_for(database=database, token=other_token, route=route)

    database.prepare_feedback(token=token, route=route)
    assert not db_has_feedback_for(database=database, token=token, route=route)
    assert not db_has_feedback_for(database=database, token=other_token, route=route)
    assert not db_has_feedback_for(database=database, token=token, route=other_route)

    rowcount = database.update_feedback(token=token, route=route, successful=True)
    assert rowcount == 1
    assert db_has_feedback_for(database=database, token=token, route=route)
    assert not db_has_feedback_for(database=database, token=other_token, route=route)
    assert not db_has_feedback_for(database=database, token=token, route=other_route)

    rowcount = database.update_feedback(token=token, route=route, successful=True)
    assert rowcount == 0


def test_feedback_stats(pathfinding_service_mock):
    token_network_address = TokenNetworkAddress(b"1" * 20)
    default_path = [b"1" * 20, b"2" * 20, b"3" * 20]
    feedback_token = FeedbackToken(token_network_address)
    database = pathfinding_service_mock.database

    database.prepare_feedback(feedback_token, default_path)
    assert database.get_num_routes_feedback() == 1
    assert database.get_num_routes_feedback(only_with_feedback=True) == 0
    assert database.get_num_routes_feedback(only_successful=True) == 0

    database.update_feedback(feedback_token, default_path, False)
    assert database.get_num_routes_feedback() == 1
    assert database.get_num_routes_feedback(only_with_feedback=True) == 1
    assert database.get_num_routes_feedback(only_successful=True) == 0

    default_path2 = default_path[1:]
    feedback_token2 = FeedbackToken(token_network_address)

    database.prepare_feedback(feedback_token2, default_path2)
    assert database.get_num_routes_feedback() == 2
    assert database.get_num_routes_feedback(only_with_feedback=True) == 1
    assert database.get_num_routes_feedback(only_successful=True) == 0

    database.update_feedback(feedback_token2, default_path2, True)
    assert database.get_num_routes_feedback() == 2
    assert database.get_num_routes_feedback(only_with_feedback=True) == 2
    assert database.get_num_routes_feedback(only_successful=True) == 1


def test_waiting_messages(pathfinding_service_mock):
    participant1_privkey, participant1 = make_privkey_address()
    token_network_address = TokenNetworkAddress(b"1" * 20)
    channel_id = ChannelID(1)

    # register token network internally
    database = pathfinding_service_mock.database
    database.conn.execute(
        "INSERT INTO token_network(address) VALUES (?)",
        [to_checksum_address(token_network_address)],
    )

    fee_update = PFSFeeUpdate(
        canonical_identifier=CanonicalIdentifier(
            chain_identifier=ChainID(1),
            token_network_address=token_network_address,
            channel_identifier=channel_id,
        ),
        updating_participant=participant1,
        fee_schedule=FeeScheduleState(),
        timestamp=datetime.utcnow(),
        signature=EMPTY_SIGNATURE,
    )
    fee_update.sign(LocalSigner(participant1_privkey))

    capacity_update = PFSCapacityUpdate(
        canonical_identifier=CanonicalIdentifier(
            chain_identifier=ChainID(1),
            token_network_address=token_network_address,
            channel_identifier=channel_id,
        ),
        updating_participant=make_address(),
        other_participant=make_address(),
        updating_nonce=Nonce(1),
        other_nonce=Nonce(1),
        updating_capacity=TokenAmount(100),
        other_capacity=TokenAmount(111),
        reveal_timeout=BlockTimeout(50),
        signature=EMPTY_SIGNATURE,
    )
    capacity_update.sign(LocalSigner(participant1_privkey))

    for message in (fee_update, capacity_update):
        database.insert_waiting_message(message)

        recovered_messages = list(
            database.pop_waiting_messages(
                token_network_address=token_network_address, channel_id=channel_id
            )
        )
        assert len(recovered_messages) == 1
        assert message == recovered_messages[0]

        recovered_messages2 = list(
            database.pop_waiting_messages(
                token_network_address=token_network_address, channel_id=channel_id
            )
        )
        assert len(recovered_messages2) == 0

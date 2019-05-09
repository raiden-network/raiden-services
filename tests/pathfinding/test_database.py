import json
from typing import List
from uuid import uuid4

from eth_utils import to_checksum_address

from pathfinding_service.database import PFSDatabase
from pathfinding_service.model.feedback import FeedbackToken
from raiden.utils.typing import Address, TokenNetworkAddress


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

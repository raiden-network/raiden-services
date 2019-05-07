from uuid import uuid4

from pathfinding_service.model.feedback import FeedbackToken
from raiden.utils import TokenNetworkAddress


def test_save_and_load_feedback_token(pathfinding_service_mock):
    token_network_address = TokenNetworkAddress(b"1" * 20)
    token = FeedbackToken(token_network_address=token_network_address)
    pathfinding_service_mock.database.insert_feedback_token(token)

    stored = pathfinding_service_mock.database.get_feedback_token(
        token_id=token.id, token_network_address=token_network_address
    )
    assert stored == token

    stored = pathfinding_service_mock.database.get_feedback_token(
        token_id=uuid4(), token_network_address=token_network_address
    )
    assert stored is None

from datetime import datetime, timedelta

from pathfinding_service.config import MAX_AGE_OF_FEEDBACK_REQUESTS
from pathfinding_service.model.feedback import FeedbackToken
from raiden.utils import TokenNetworkAddress


def test_feedback_token_validity():
    token_network_address = TokenNetworkAddress(b"1" * 20)

    # Newly created token is valid
    valid_token = FeedbackToken(token_network_address=token_network_address)
    assert valid_token.is_valid()

    # Test expiry in is_valid
    invalid_token = FeedbackToken(
        creation_time=datetime.utcnow() - MAX_AGE_OF_FEEDBACK_REQUESTS - timedelta(seconds=1),
        token_network_address=token_network_address,
    )
    assert not invalid_token.is_valid()

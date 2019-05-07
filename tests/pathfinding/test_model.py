from datetime import datetime, timedelta
from uuid import uuid4

from pathfinding_service.config import MAX_AGE_OF_FEEDBACK_REQUESTS
from pathfinding_service.model import FeedbackToken


def test_feedback_token_validity():
    valid_token = FeedbackToken(id=uuid4(), creation_time=datetime.utcnow())
    assert valid_token.is_valid()

    invalid_token = FeedbackToken(
        id=uuid4(),
        creation_time=datetime.utcnow() - MAX_AGE_OF_FEEDBACK_REQUESTS - timedelta(seconds=1),
    )
    assert not invalid_token.is_valid()

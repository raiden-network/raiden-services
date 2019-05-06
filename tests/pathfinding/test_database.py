from datetime import datetime
from uuid import uuid4

from pathfinding_service.model import FeedbackToken


def test_save_and_load_feedback_token(pathfinding_service_mock):
    token = FeedbackToken(id=uuid4(), creation_time=datetime.utcnow())
    pathfinding_service_mock.database.insert_feedback_token(token)

    stored = pathfinding_service_mock.database.get_feedback_token(token_id=token.id)
    assert stored == token

    stored = pathfinding_service_mock.database.get_feedback_token(token_id=uuid4())
    assert stored is None

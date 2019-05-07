from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pathfinding_service.config import MAX_AGE_OF_FEEDBACK_REQUESTS

from .channel_view import ChannelView
from .iou import IOU
from .token_network import TokenNetwork

__all__ = ["ChannelView", "TokenNetwork", "IOU", "FeedbackToken"]


@dataclass
class FeedbackToken:
    id: UUID
    creation_time: datetime

    def is_valid(self) -> bool:
        """ Checks if the token is valid."""
        return self.creation_time + MAX_AGE_OF_FEEDBACK_REQUESTS > datetime.utcnow()

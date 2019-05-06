from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .channel_view import ChannelView
from .iou import IOU
from .token_network import TokenNetwork

__all__ = ["ChannelView", "TokenNetwork", "IOU", "FeedbackToken"]


@dataclass
class FeedbackToken:
    id: UUID
    expiry: datetime

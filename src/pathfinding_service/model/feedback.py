from dataclasses import dataclass
from datetime import datetime
from typing import List
from uuid import UUID

from pathfinding_service.config import MAX_AGE_OF_FEEDBACK_REQUESTS
from raiden.utils import Address, TokenNetworkAddress


@dataclass
class FeedbackToken:
    id: UUID
    creation_time: datetime
    token_network_address: TokenNetworkAddress

    def is_valid(self) -> bool:
        """ Checks if the token is valid."""
        return self.creation_time + MAX_AGE_OF_FEEDBACK_REQUESTS > datetime.utcnow()


@dataclass
class RouteFeedback:
    status: str
    received_time: datetime
    path: List[Address]

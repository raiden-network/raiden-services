from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from pathfinding_service.config import MAX_AGE_OF_FEEDBACK_REQUESTS
from raiden.utils.typing import TokenNetworkAddress


@dataclass
class FeedbackToken:
    token_network_address: TokenNetworkAddress
    id: UUID = field(default_factory=uuid4)
    creation_time: datetime = field(default_factory=datetime.utcnow)

    def is_valid(self) -> bool:
        """ Checks if the token is valid."""
        return self.creation_time + MAX_AGE_OF_FEEDBACK_REQUESTS > datetime.utcnow()

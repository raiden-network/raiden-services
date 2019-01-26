from dataclasses import dataclass, field
from typing import List, Optional

from raiden_contracts.constants import ChannelState


@dataclass
class Channel:
    token_network_address: str
    identifier: int
    participant1: str
    participant2: str
    settle_timeout: int
    state: ChannelState = ChannelState.OPENED
    closing_block: Optional[int] = None


@dataclass
class MonitoringServiceState:
    token_network_registry_address: str
    latest_known_block: int
    token_network_addresses: List[str] = field(default_factory=list)

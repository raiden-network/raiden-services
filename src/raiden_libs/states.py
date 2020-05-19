from dataclasses import dataclass, field
from typing import List, Optional

from monitoring_service.constants import DEFAULT_FILTER_INTERVAL
from raiden.utils.typing import Address, BlockNumber, BlockTimeout, ChainID, TokenNetworkAddress


@dataclass
class BlockchainState:
    chain_id: ChainID
    token_network_registry_address: Address
    latest_committed_block: BlockNumber
    monitor_contract_address: Optional[Address] = None
    token_network_addresses: List[TokenNetworkAddress] = field(default_factory=list)
    current_event_filter_interval: BlockTimeout = DEFAULT_FILTER_INTERVAL

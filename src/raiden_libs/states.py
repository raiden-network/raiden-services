from dataclasses import dataclass, field
from typing import List, Optional

from raiden.utils.typing import Address, BlockNumber, ChainID, TokenNetworkAddress


@dataclass
class BlockchainState:
    chain_id: ChainID
    token_network_registry_address: Address
    latest_known_block: BlockNumber
    monitor_contract_address: Optional[Address] = None
    token_network_addresses: List[TokenNetworkAddress] = field(default_factory=list)

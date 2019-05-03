from dataclasses import dataclass, field
from typing import List

from raiden.utils.typing import Address, BlockNumber, ChainID, TokenNetworkAddress


@dataclass
class BlockchainState:
    chain_id: ChainID
    token_network_registry_address: Address
    monitor_contract_address: Address
    latest_known_block: BlockNumber
    token_network_addresses: List[TokenNetworkAddress] = field(default_factory=list)

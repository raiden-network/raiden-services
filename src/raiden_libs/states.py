from dataclasses import dataclass
from typing import Optional

from raiden_common.utils.typing import Address, BlockNumber, BlockTimeout

from monitoring_service.constants import DEFAULT_FILTER_INTERVAL
from raiden_contracts.utils.type_aliases import ChainID


@dataclass
class BlockchainState:
    chain_id: ChainID
    token_network_registry_address: Address
    latest_committed_block: BlockNumber
    monitor_contract_address: Optional[Address] = None
    current_event_filter_interval: BlockTimeout = DEFAULT_FILTER_INTERVAL

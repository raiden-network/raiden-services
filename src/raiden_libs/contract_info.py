import sys
from typing import Any, Dict, List

import structlog

from raiden.utils.typing import BlockNumber, ChainID
from raiden_contracts.contract_manager import (
    ContractManager,
    contracts_precompiled_path,
    get_contracts_deployment_info,
)
from raiden_libs.types import Address

log = structlog.get_logger(__name__)
START_BLOCK_ID = 'block'
CONTRACT_MANAGER = ContractManager(contracts_precompiled_path())


def get_contract_addresses_and_start_block(
    chain_id: ChainID,
    contracts: List[str],
    address_overwrites: Dict[str, Address],
    contracts_version: str = None,
) -> Dict[str, Any]:
    """ Returns contract addresses and start query block for a given chain and contracts version.

    The default contracts can be overwritten by the additional parameters.

    Args:
        chain_id: The chain id to look for deployed contracts.
        contracts: The list of contracts which should be considered
        address_overwrites: Dict of addresses which should be used instead of
            the ones in the requested deployment.
        contracts_version: The version of the contracts to use.

    Returns: A dictionary with the contract addresses and start block for the given information
    """
    try:
        contract_data = get_contracts_deployment_info(chain_id=chain_id, version=contracts_version)
    except ValueError:
        log.error(
            'No deployed contracts were found at the default registry',
            contracts_version=contracts_version,
        )
        sys.exit(1)

    # Get deployed addresses for those contracts which have no overwrites
    data: Dict[str, Any] = {}
    for c in contracts:
        data[c] = address_overwrites.get(c, contract_data['contracts'][c]['address'])

    # Set start block to zero if any contract addresses are overwritten
    if any(address_overwrites.values()):
        data[START_BLOCK_ID] = BlockNumber(0)
    else:
        data[START_BLOCK_ID] = max(
            0, min(contract_data['contracts'][c]['block_number'] for c in contracts)
        )

    return data

from typing import Any, Dict, List, Optional

import structlog

from raiden.utils.typing import BlockNumber, ChainID
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_contracts.contract_manager import (
    ContractManager,
    contracts_precompiled_path,
    get_contracts_deployment_info,
)
from raiden_libs.types import Address

log = structlog.get_logger(__name__)
START_BLOCK_ID = 'block'
CONTRACT_MANAGER = ContractManager(contracts_precompiled_path())


def get_deployment_infos(
    chain_id: ChainID, contracts: List[str], contracts_version: str = None
) -> Dict[str, Any]:
    try:
        contract_data = get_contracts_deployment_info(chain_id=chain_id, version=contracts_version)

        deployment_info: Dict[str, Address] = {
            c: contract_data['contracts'][c]['address'] for c in contracts
        }
        contracts_start_block = max(
            0, min(contract_data['contracts'][c]['block_number'] for c in contracts)
        )
        deployment_info[START_BLOCK_ID] = contracts_start_block
        return deployment_info
    except ValueError:
        # TODO
        log.info('No deployed contracts were found at the default registry')

        return {
            CONTRACT_TOKEN_NETWORK_REGISTRY: None,
            CONTRACT_MONITORING_SERVICE: None,
            CONTRACT_USER_DEPOSIT: None,
            START_BLOCK_ID: 0,
        }


def get_contract_addresses_and_start_block(
    chain_id: ChainID,
    contracts: List[str],
    address_overwrites: Dict[str, Address],
    contracts_version: str = None,
) -> Optional[Dict[str, Any]]:
    """ Returns contract addresses and start query block for a given chain and contracts version.

    The default contracts can be overwritten by the additional parameters.

    Args:
        chain_id: The chain id to look for deployed contracts.
        contracts_version: The version of the contracts to use.
        token_network_registry_address: Address to overwrite the predeployed token network
            registry.
        monitor_contract_address: Address to overwrite the predeployed monitor contract.
        user_deposit_contract_address: Address to overwrite the predeployed user deposit
            contract.
        start_block: Start block to use when all addresses are overwritten.

    Returns: A dictionary with the contract addresses and start block for the given information,
        or `None` if the contracts aren't deployed for the given configurations and not all
        options have been supplied.
    """
    data = get_deployment_infos(chain_id, contracts, contracts_version)

    # overwrite defaults with user settings
    for contract, address in address_overwrites.items():
        data[contract] = address

    # Set start block to zero if any contract addresses are overwritten
    if any(address_overwrites.values()):
        data[START_BLOCK_ID] = BlockNumber(0)

    return data

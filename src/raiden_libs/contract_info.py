from typing import Any, Dict, Optional

import structlog

from raiden.utils.typing import BlockNumber, ChainID
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_contracts.contract_manager import get_contracts_deployment_info
from raiden_libs.types import Address

log = structlog.get_logger(__name__)
START_BLOCK_ID = 'block'


def get_deployment_infos(
    chain_id: ChainID,
    contracts_version: str = None,
) -> Dict[str, Any]:
    try:
        contract_data = get_contracts_deployment_info(
            chain_id=chain_id,
            version=contracts_version,
        )
        token_network_registry_info = contract_data['contracts'][CONTRACT_TOKEN_NETWORK_REGISTRY]
        monitor_contract_info = contract_data['contracts'][CONTRACT_MONITORING_SERVICE]
        user_deposit_contract_info = contract_data['contracts'][CONTRACT_USER_DEPOSIT]

        contracts_start_block = max(
            0,
            min(
                token_network_registry_info['block_number'],
                monitor_contract_info['block_number'],
                user_deposit_contract_info['block_number'],
            ),
        )
        return {
            CONTRACT_TOKEN_NETWORK_REGISTRY: token_network_registry_info['address'],
            CONTRACT_MONITORING_SERVICE: monitor_contract_info['address'],
            CONTRACT_USER_DEPOSIT: user_deposit_contract_info['address'],
            START_BLOCK_ID: contracts_start_block,
        }
    except ValueError:
        log.info('No deployed contracts were found at the default registry')

        return {
            CONTRACT_TOKEN_NETWORK_REGISTRY: None,
            CONTRACT_MONITORING_SERVICE: None,
            CONTRACT_USER_DEPOSIT: None,
            START_BLOCK_ID: 0,
        }


def get_contract_addresses_and_start_block(
    chain_id: ChainID,
    contracts_version: str = None,
    token_network_registry_address: Address = None,
    monitor_contract_address: Address = None,
    user_deposit_contract_address: Address = None,
    start_block: BlockNumber = BlockNumber(0),
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
    data = get_deployment_infos(chain_id, contracts_version)

    # overwrite defaults with user settings
    if token_network_registry_address:
        data[CONTRACT_TOKEN_NETWORK_REGISTRY] = token_network_registry_address
    if monitor_contract_address:
        data[CONTRACT_MONITORING_SERVICE] = monitor_contract_address
    if user_deposit_contract_address:
        data[CONTRACT_USER_DEPOSIT] = user_deposit_contract_address

    # Overwrite start block when all contracts have been overwritten
    all_addresses_given = all([
        token_network_registry_address,
        monitor_contract_address,
        user_deposit_contract_address,
    ])
    if all_addresses_given:
        data[START_BLOCK_ID] = start_block

    # Return infos when all contracts are set, otherwise `None`
    all_addresses_set = all(v is not None for v in data.values())
    if all_addresses_set:
        return data
    else:
        return None

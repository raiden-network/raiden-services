from typing import Dict, Optional

import structlog

from raiden.utils.typing import Address, BlockNumber, ChainID
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_contracts.contract_manager import get_contracts_deployed

log = structlog.get_logger(__name__)
START_BLOCK_SAFETY_MARGIN = 100
START_BLOCK_ID = 'block'


def get_contract_addresses_and_start_block(
    chain_id: ChainID,
    contracts_version: str = None,
    start_block_safety_margin: int = START_BLOCK_SAFETY_MARGIN,
    token_network_registry_address: Address = None,
    monitor_contract_address: Address = None,
    user_deposit_contract_address: Address = None,
    start_block: BlockNumber = 0,
) -> Optional[Dict]:
    """ Returns contract addresses and start query block for a given chain and contracts version.

    The default contracts can be overwritten by the additional parameters.

    Args:
        chain_id: The chain id to look for deployed contracts.
        contracts_version: The versaion of the contracts to use.
        start_block_safety_margin: The safety margin of the start block
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
    all_addresses_given = all([
        token_network_registry_address,
        monitor_contract_address,
        user_deposit_contract_address,
    ])
    given_start_block = max(0, start_block)
    try:
        core_contract_data = get_contracts_deployed(
            chain_id=chain_id,
            version=contracts_version,
        )
        service_contract_data = get_contracts_deployed(
            chain_id=chain_id,
            version=contracts_version,
            services=True,
        )
        token_network_registry_info = core_contract_data['contracts'][CONTRACT_TOKEN_NETWORK_REGISTRY]
        monitor_contract_info = service_contract_data['contracts'][CONTRACT_MONITORING_SERVICE]
        user_deposit_contract_info = service_contract_data['contracts'][CONTRACT_USER_DEPOSIT]

        registry_address = token_network_registry_address or token_network_registry_info['address']
        monitor_address = monitor_contract_address or monitor_contract_info['address']
        udc_address = user_deposit_contract_address or user_deposit_contract_info['address']

        contracts_start_block = max(
            0,
            min(
                token_network_registry_info['block_number'],
                monitor_contract_info['block_number'],
                user_deposit_contract_info['block_number'],
            ) - start_block_safety_margin,
        )
        return {
            CONTRACT_TOKEN_NETWORK_REGISTRY: registry_address,
            CONTRACT_MONITORING_SERVICE: monitor_address,
            CONTRACT_USER_DEPOSIT: udc_address,
            START_BLOCK_ID: given_start_block if all_addresses_given else contracts_start_block,
        }
    except ValueError:
        log.info('No deployed contracts were found at the default registry')

        if all_addresses_given:
            return {
                CONTRACT_TOKEN_NETWORK_REGISTRY: token_network_registry_address,
                CONTRACT_MONITORING_SERVICE: monitor_contract_address,
                CONTRACT_USER_DEPOSIT: user_deposit_contract_address,
                START_BLOCK_ID: given_start_block,
            }
        else:
            return None

from eth_utils import is_checksum_address, to_checksum_address
from web3 import Web3
from raiden_contracts.contract_manager import CONTRACT_MANAGER
from raiden_libs.private_contract import PrivateContract
from web3.utils.transactions import wait_for_transaction_receipt


def is_service_registered(
    web3: Web3,
    msc_contract_address: str,
    service_address: str
) -> bool:
    """Returns true if service is registered in the Monitoring service contract"""
    assert is_checksum_address(msc_contract_address)
    assert is_checksum_address(service_address)
    contract_abi = CONTRACT_MANAGER.get_contract_abi('MonitoringService')
    contract = web3.eth.contract(abi=contract_abi, address=msc_contract_address)
    return contract.functions.registered_monitoring_services(service_address).call()


def register_service(
    web3: Web3,
    msc_contract_address: str,
    service_address: str,
    private_key: str
):
    """Register service with a Monitor service contract"""
    assert is_checksum_address(msc_contract_address)
    assert is_checksum_address(service_address)
    contract_abi = CONTRACT_MANAGER.get_contract_abi('MonitoringService')
    contract = PrivateContract(web3.eth.contract(abi=contract_abi, address=msc_contract_address))

    # approve funds for MSC
    deposit = contract.functions.minimum_deposit().call()
    token_address = to_checksum_address(contract.functions.token().call())
    token_abi = CONTRACT_MANAGER.get_contract_abi('Token')
    token_contract = web3.eth.contract(abi=token_abi, address=token_address)
    token_contract = PrivateContract(token_contract)
    tx = token_contract.functions.approve(msc_contract_address, deposit).transact(
        private_key=private_key
    )
    wait_for_transaction_receipt(web3, tx)

    # register MS
    tx = contract.functions.depositAndRegisterMonitoringService().transact(
        private_key=private_key
    )
    # check if MS is really registered
    wait_for_transaction_receipt(web3, tx)
    return contract.functions.registered_monitoring_services(service_address).call()

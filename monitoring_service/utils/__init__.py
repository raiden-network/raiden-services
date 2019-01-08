from eth_utils import is_checksum_address, to_checksum_address
from web3 import Web3
from web3.utils.transactions import wait_for_transaction_receipt

from raiden_libs.private_contract import PrivateContract
from raiden_libs.utils import private_key_to_address
from raiden_contracts.constants import CONTRACT_MONITORING_SERVICE, CONTRACT_RAIDEN_SERVICE_BUNDLE
from raiden_contracts.contract_manager import ContractManager


from .blockchain_listener import BlockchainListener, BlockchainMonitor

__all__ = [
    'BlockchainListener',
    'BlockchainMonitor',
]


def is_service_registered(
    web3: Web3,
    contract_manager: ContractManager,
    msc_contract_address: str,
    service_address: str,
) -> bool:
    """Returns true if service is registered in the Monitoring service contract"""
    assert is_checksum_address(msc_contract_address)
    assert is_checksum_address(service_address)
    monitor_contract_abi = contract_manager.get_contract_abi(CONTRACT_MONITORING_SERVICE)
    monitor_contract = web3.eth.contract(abi=monitor_contract_abi, address=msc_contract_address)
    bundle_contract_abi = contract_manager.get_contract_abi(CONTRACT_RAIDEN_SERVICE_BUNDLE)
    raiden_service_bundle_address = to_checksum_address(monitor_contract.functions.rsb().call())
    bundle_contract = web3.eth.contract(
        abi=bundle_contract_abi,
        address=raiden_service_bundle_address,
    )
    return bundle_contract.functions.deposits(service_address).call() > 0


def register_service(
    web3: Web3,
    contract_manager: ContractManager,
    msc_contract_address: str,
    private_key: str,
    deposit: int = 10,  # any amount works now
):
    """Register service with a Monitor service contract"""
    service_address = private_key_to_address(private_key)
    assert is_checksum_address(msc_contract_address)
    assert is_checksum_address(service_address)
    monitor_contract_abi = contract_manager.get_contract_abi(CONTRACT_MONITORING_SERVICE)
    monitor_contract = PrivateContract(web3.eth.contract(
        abi=monitor_contract_abi,
        address=msc_contract_address,
    ))
    bundle_contract_abi = contract_manager.get_contract_abi(CONTRACT_RAIDEN_SERVICE_BUNDLE)
    raiden_service_bundle_address = to_checksum_address(monitor_contract.functions.rsb().call())
    bundle_contract = PrivateContract(web3.eth.contract(
        abi=bundle_contract_abi,
        address=raiden_service_bundle_address,
    ))

    # approve funds for MSC
    token_address = to_checksum_address(monitor_contract.functions.token().call())
    token_abi = contract_manager.get_contract_abi('Token')
    token_contract = web3.eth.contract(abi=token_abi, address=token_address)
    token_contract = PrivateContract(token_contract)
    tx = token_contract.functions.approve(raiden_service_bundle_address, deposit).transact(
        private_key=private_key,
    )
    wait_for_transaction_receipt(web3, tx)

    # register MS
    tx = bundle_contract.functions.deposit(deposit).transact(
        private_key=private_key,
    )
    # check if MS is really registered
    wait_for_transaction_receipt(web3, tx)
    return bundle_contract.functions.deposits(service_address).call() > 0

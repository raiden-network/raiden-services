import logging

import gevent.event  # noqa  needed for DummyTransport fixture
import pytest
from eth_utils import is_checksum_address, to_checksum_address
from request_collector.server import RequestCollector
from web3 import Web3
from web3.utils.transactions import wait_for_transaction_receipt

from monitoring_service.cli import MonitoringService
from raiden_contracts.constants import CONTRACT_MONITORING_SERVICE, CONTRACT_RAIDEN_SERVICE_BUNDLE
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.private_contract import PrivateContract
from raiden_libs.test.mocks.dummy_transport import DummyTransport
from raiden_libs.utils import private_key_to_address

log = logging.getLogger(__name__)

TEST_POLL_INTERVAL = 0.001


@pytest.fixture
def server_private_key(get_random_privkey, ethereum_tester):
    key = get_random_privkey()
    ethereum_tester.add_account(key)
    return key


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


@pytest.fixture
def dummy_transport():
    return DummyTransport()


@pytest.fixture
def monitoring_service(
    server_private_key,
    web3,
    monitoring_service_contract,
    token_network_registry_contract,
    send_funds,
    contracts_manager: ContractManager,
):
    # send some eth & tokens to MS
    send_funds(private_key_to_address(server_private_key))
    register_service(
        web3=web3,
        contract_manager=contracts_manager,
        msc_contract_address=monitoring_service_contract.address,
        private_key=server_private_key,
    )

    ms = MonitoringService(
        web3=web3,
        contract_manager=contracts_manager,
        private_key=server_private_key,
        registry_address=token_network_registry_contract.address,
        monitor_contract_address=monitoring_service_contract.address,
        required_confirmations=1,  # for faster tests
        poll_interval=1,  # for faster tests
    )
    return ms


@pytest.fixture
def request_collector(
    server_private_key,
    dummy_transport,
    state_db_sqlite,
    web3,
    monitoring_service_contract,
    token_network_registry_contract,
    send_funds,
    contracts_manager: ContractManager,
):
    rc = RequestCollector(
        state_db=state_db_sqlite,
        transport=dummy_transport,
    )
    rc.start()
    yield rc
    rc.stop()

import logging

import pytest
from request_collector.server import RequestCollector

from monitoring_service.database import Database
from monitoring_service.service import MonitoringService
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.utils import private_key_to_address

log = logging.getLogger(__name__)

TEST_POLL_INTERVAL = 0.001


@pytest.fixture
def server_private_key(get_random_privkey, ethereum_tester):
    key = get_random_privkey()
    ethereum_tester.add_account(key)
    return key


@pytest.fixture
def ms_database():
    return Database(
        filename=':memory:',
        chain_id=1,
        msc_address='0x' + '2' * 40,
        registry_address='0x' + '3' * 40,
        receiver='0x' + '4' * 40,
    )


@pytest.fixture
def monitoring_service(
    server_private_key,
    web3,
    monitoring_service_contract,
    token_network_registry_contract,
    send_funds,
    contracts_manager: ContractManager,
    service_registry,
    custom_token,
):
    # register MS in ServiceRegistry
    ms_address = private_key_to_address(server_private_key)
    send_funds(ms_address)
    deposit = 10  # any amount is sufficient for regsitration, right now
    custom_token.functions.mint(deposit).transact({'from': ms_address})
    custom_token.functions.approve(
        service_registry.address,
        deposit,
    ).transact({'from': ms_address})
    service_registry.functions.deposit(deposit).transact({'from': ms_address})

    ms = MonitoringService(
        web3=web3,
        contract_manager=contracts_manager,
        private_key=server_private_key,
        registry_address=token_network_registry_contract.address,
        monitor_contract_address=monitoring_service_contract.address,
        required_confirmations=1,  # for faster tests
        poll_interval=1,  # for faster tests
        db_filename=':memory:',
    )
    return ms


@pytest.fixture
def request_collector(
    server_private_key,
    ms_database,
    web3,
    monitoring_service_contract,
    token_network_registry_contract,
    send_funds,
    contracts_manager: ContractManager,
):
    rc = RequestCollector(
        private_key=server_private_key,
        state_db=ms_database,
    )
    rc.start()
    yield rc
    rc.stop()

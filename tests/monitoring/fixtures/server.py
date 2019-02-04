import logging

import gevent.event  # noqa  needed for DummyTransport fixture
import pytest
from request_collector.server import RequestCollector

from monitoring_service.service import MonitoringService
from raiden_contracts.contract_manager import ContractManager
from raiden_libs.test.mocks.dummy_transport import DummyTransport
from raiden_libs.utils import private_key_to_address

log = logging.getLogger(__name__)

TEST_POLL_INTERVAL = 0.001


@pytest.fixture
def server_private_key(get_random_privkey, ethereum_tester):
    key = get_random_privkey()
    ethereum_tester.add_account(key)
    return key


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

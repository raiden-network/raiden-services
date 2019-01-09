import logging

import pytest

from monitoring_service import MonitoringService
from monitoring_service.utils import BlockchainMonitor, register_service
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK
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
def blockchain(web3, contracts_manager, token_network):
    blockchain = BlockchainMonitor(
        web3=web3,
        contract_manager=contracts_manager,
        contract_name=CONTRACT_TOKEN_NETWORK,
        contract_address=token_network.address,
        required_confirmations=1,
        poll_interval=TEST_POLL_INTERVAL,
    )
    yield blockchain
    blockchain.stop()


@pytest.fixture
def monitoring_service(
    server_private_key,
    blockchain,
    dummy_transport,
    state_db_mock,
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
        state_db=state_db_mock,
        transport=dummy_transport,
        registry_address=token_network_registry_contract.address,
        monitor_contract_address=monitoring_service_contract.address,
        required_confirmations=1,  # for faster tests
        poll_interval=0,  # for faster tests
    )
    yield ms
    ms.stop()

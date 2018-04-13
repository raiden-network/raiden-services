import pytest
from raiden_libs.test.mocks.dummy_transport import DummyTransport

from monitoring_service import MonitoringService
from monitoring_service.blockchain import BlockchainMonitor
from monitoring_service.api.rest import ServiceApi


@pytest.fixture
def server_private_key():
    return '0x1'


@pytest.fixture
def dummy_transport():
    return DummyTransport()


@pytest.fixture
def blockchain(web3):
    blockchain = BlockchainMonitor(web3)
    blockchain.poll_interval = 1
    return blockchain


@pytest.fixture
def monitoring_service(
        server_private_key,
        blockchain,
        dummy_transport,
        state_db_mock,
        web3,
        monitoring_service_contract
):
    ms = MonitoringService(
        server_private_key,
        transport=dummy_transport,
        blockchain=blockchain,
        state_db=state_db_mock,
        ms_contract_address=monitoring_service_contract.address
    )
    yield ms
    ms.blockchain.stop()
    ms.stop()


@pytest.fixture
def rest_api(monitoring_service, blockchain, rest_host, rest_port):
    api = ServiceApi(monitoring_service, blockchain)
    api.run(rest_host, rest_port)
    return api

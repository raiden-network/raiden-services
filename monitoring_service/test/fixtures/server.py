import pytest
from monitoring_service.test.mockups.dummy_transport import DummyTransport

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
def blockchain():
    return BlockchainMonitor()


@pytest.fixture
def monitoring_service(server_private_key, blockchain, dummy_transport, state_db):
    return MonitoringService(
        server_private_key,
        transport=dummy_transport,
        blockchain=blockchain,
        state_db=state_db
    )


@pytest.fixture
def rest_api(monitoring_service, blockchain, rest_host, rest_port):
    api = ServiceApi(monitoring_service, blockchain)
    api.run(rest_host, rest_port)
    return api

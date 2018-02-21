import pytest
from monitoring_service.test.mockups.dummy_transport import DummyTransport

from monitoring_service import MonitoringService
from monitoring_service.blockchain import BlockchainMonitor


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
def monitoring_service(server_private_key, blockchain, dummy_transport):
    return MonitoringService(
        server_private_key,
        dummy_transport,
        blockchain
    )

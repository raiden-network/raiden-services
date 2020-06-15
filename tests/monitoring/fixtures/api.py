# pylint: disable=redefined-outer-name
from typing import Generator, Iterator
from unittest.mock import Mock

import pytest
from eth_typing import BlockNumber
from eth_utils import decode_hex, to_checksum_address
from tests.libs.mocks.web3 import Web3Mock

from monitoring_service.api import MSApi
from monitoring_service.constants import API_PATH
from monitoring_service.service import MonitoringService
from raiden.utils.typing import BlockTimeout
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_SERVICE_REGISTRY,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.constants import DEFAULT_API_HOST


@pytest.fixture(scope="session")
def api_url(free_port: int) -> str:
    return "http://localhost:{}{}".format(free_port, API_PATH)


@pytest.fixture
def monitoring_service_mock() -> Generator[MonitoringService, None, None]:
    web3_mock = Web3Mock()

    mock_udc = Mock(address=bytes([8] * 20))
    mock_udc.functions.effectiveBalance.return_value.call.return_value = 10000
    mock_udc.functions.token.return_value.call.return_value = to_checksum_address(bytes([7] * 20))
    ms = MonitoringService(
        web3=web3_mock,
        private_key=PrivateKey(
            decode_hex("3a1076bf45ab87712ad64ccb3b10217737f7faacbf2872e88fdd9a537d8fe266")
        ),
        db_filename=":memory:",
        contracts={
            CONTRACT_TOKEN_NETWORK_REGISTRY: Mock(address=bytes([9] * 20)),
            CONTRACT_USER_DEPOSIT: mock_udc,
            CONTRACT_MONITORING_SERVICE: Mock(address=bytes([1] * 20)),
            CONTRACT_SERVICE_REGISTRY: Mock(address=bytes([2] * 20)),
        },
        sync_start_block=BlockNumber(0),
        required_confirmations=BlockTimeout(0),
        poll_interval=0,
    )

    yield ms


@pytest.fixture
def ms_api_sut(monitoring_service_mock: MonitoringService, free_port: int) -> Iterator[MSApi]:
    api = MSApi(monitoring_service=monitoring_service_mock, operator="")
    api.run(host=DEFAULT_API_HOST, port=free_port)
    yield api
    api.stop()

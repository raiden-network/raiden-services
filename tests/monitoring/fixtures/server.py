# pylint: disable=redefined-outer-name
import logging
from typing import List
from unittest.mock import patch

import pytest
from eth_utils import decode_hex
from request_collector.server import RequestCollector
from web3 import Web3

from monitoring_service.database import Database
from monitoring_service.service import MonitoringService
from raiden.utils.typing import Address
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)

log = logging.getLogger(__name__)

TEST_POLL_INTERVAL = 0.001


@pytest.fixture(scope="session")
def ms_address(create_account) -> Address:
    return decode_hex(create_account())


@pytest.fixture
def default_cli_args_ms(default_cli_args) -> List[str]:
    return default_cli_args + [
        "--token-network-registry-address",
        "0x" + "1" * 40,
        "--monitor-contract-address",
        "0x" + "2" * 40,
        "--user-deposit-contract-address",
        "0x" + "3" * 40,
    ]


@pytest.fixture
def ms_database():
    return Database(
        filename=":memory:",
        chain_id=1,
        msc_address=Address(bytes([2] * 20)),
        registry_address=Address(bytes([3] * 20)),
        receiver=Address(bytes([4] * 20)),
    )


@pytest.fixture
def register_service(custom_token, service_registry):
    def f(address, deposit=10):
        deposit = 10  # any amount is sufficient for registration, right now
        custom_token.functions.mint(deposit).transact({"from": address})
        custom_token.functions.approve(service_registry.address, deposit).transact(
            {"from": address}
        )
        service_registry.functions.deposit(deposit).transact({"from": address})

    return f


@pytest.fixture
def monitoring_service(  # pylint: disable=too-many-arguments
    ms_address,
    web3: Web3,
    monitoring_service_contract,
    user_deposit_contract,
    token_network_registry_contract,
    ms_database,
    get_private_key,
    register_service,
):
    register_service(ms_address)
    ms = MonitoringService(
        web3=web3,
        private_key=get_private_key(ms_address),
        contracts={
            CONTRACT_TOKEN_NETWORK_REGISTRY: token_network_registry_contract,
            CONTRACT_MONITORING_SERVICE: monitoring_service_contract,
            CONTRACT_USER_DEPOSIT: user_deposit_contract,
        },
        required_confirmations=0,  # for faster tests
        poll_interval=0.01,  # for faster tests
        db_filename=":memory:",
    )
    # We need a shared db between MS and RC so the MS can use MR saved by the RC
    ms.context.db = ms_database
    return ms


@pytest.fixture
def request_collector(ms_address, ms_database, get_private_key):
    with patch("request_collector.server.MatrixListener"):
        rc = RequestCollector(private_key=get_private_key(ms_address), state_db=ms_database)
        rc.start()
        yield rc
        rc.stop()
        rc.join()

import logging
from typing import List
from unittest.mock import patch

import pytest
from request_collector.server import RequestCollector
from web3 import Web3

from monitoring_service.database import Database
from monitoring_service.service import MonitoringService
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_contracts.contract_manager import ContractManager
from raiden_contracts.tests.utils import get_random_privkey
from raiden_libs.types import Address
from raiden_libs.utils import private_key_to_address

log = logging.getLogger(__name__)

TEST_POLL_INTERVAL = 0.001


@pytest.fixture
def server_private_key(ethereum_tester):
    key = get_random_privkey()
    ethereum_tester.add_account(key)
    return key


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
        msc_address=Address("0x" + "2" * 40),
        registry_address=Address("0x" + "3" * 40),
        receiver=Address("0x" + "4" * 40),
    )


@pytest.fixture
def monitoring_service(
    server_private_key,
    web3: Web3,
    monitoring_service_contract,
    user_deposit_contract,
    token_network_registry_contract,
    send_funds,
    contracts_manager: ContractManager,
    service_registry,
    custom_token,
    ms_database,
):
    # register MS in ServiceRegistry
    ms_address = private_key_to_address(server_private_key)
    send_funds(ms_address)
    deposit = 10  # any amount is sufficient for regsitration, right now
    custom_token.functions.mint(deposit).transact({"from": ms_address})
    custom_token.functions.approve(service_registry.address, deposit).transact(
        {"from": ms_address}
    )
    service_registry.functions.deposit(deposit).transact({"from": ms_address})

    ms = MonitoringService(
        web3=web3,
        private_key=server_private_key,
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
def request_collector(
    server_private_key,
    ms_database,
    web3,
    monitoring_service_contract,
    token_network_registry_contract,
    send_funds,
    contracts_manager: ContractManager,
):
    with patch("request_collector.server.MatrixListener"):
        rc = RequestCollector(private_key=server_private_key, state_db=ms_database)
        rc.start()
        yield rc
        rc.stop()
        rc.join()

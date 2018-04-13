import pytest
import logging
from raiden_contracts.contract_manager import (
    ContractManager,
    CONTRACTS_SOURCE_DIRS,
)

log = logging.getLogger(__name__)


@pytest.fixture
def contracts_source_dir():
    return CONTRACTS_SOURCE_DIRS


@pytest.fixture
def contracts_manager(contracts_source_dir):
    return ContractManager(contracts_source_dir)


@pytest.fixture
def contract_deployer_address(faucet_address):
    return faucet_address


@pytest.fixture
def monitoring_service_contract(deploy_tester_contract, standard_token_contract):
    return deploy_tester_contract(
        'MonitoringService',
        args=[standard_token_contract.address, 100]
    )

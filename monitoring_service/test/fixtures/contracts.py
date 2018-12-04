import pytest
import logging
from raiden_contracts.contract_manager import ContractManager, contracts_source_path

log = logging.getLogger(__name__)


@pytest.fixture
def contracts_manager():
    return ContractManager(contracts_source_path())


@pytest.fixture
def contract_deployer_address(faucet_address):
    return faucet_address


@pytest.fixture
def monitoring_service_contract(monitoring_service_external):
    return monitoring_service_external

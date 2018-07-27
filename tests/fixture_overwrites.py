# -*- coding: utf-8 -*-
import pytest
from raiden_contracts.contract_manager import ContractManager, CONTRACTS_SOURCE_DIRS
from raiden_contracts.constants import CONTRACT_TOKEN_NETWORK
from raiden_libs.blockchain import BlockchainListener


@pytest.fixture(scope='session')
def contracts_manager():
    return ContractManager(CONTRACTS_SOURCE_DIRS)


@pytest.fixture(scope='session')
def contract_deployer_address(faucet_address):
    return faucet_address


@pytest.fixture
def blockchain_listener(web3, contracts_manager):
    blockchain_listener = BlockchainListener(
        web3=web3,
        contract_manager=contracts_manager,
        contract_name=CONTRACT_TOKEN_NETWORK,
        poll_interval=0,
    )
    return blockchain_listener

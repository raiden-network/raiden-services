import pytest
import logging
from raiden_contracts.contract_manager import (
    ContractManager,
    CONTRACTS_SOURCE_DIRS,
    get_event_from_abi
)
from web3.utils.events import get_event_data
from eth_utils import is_address

log = logging.getLogger(__name__)


@pytest.fixture
def contracts_source_dir():
    return CONTRACTS_SOURCE_DIRS


@pytest.fixture
def contracts_manager(contracts_source_dir):
    return ContractManager(contracts_source_dir)


@pytest.fixture
def get_contract_abi(contracts_manager):
    return contracts_manager.get_contract_abi


@pytest.fixture
def contract_deployer_address(faucet_address):
    return faucet_address


@pytest.fixture
def deploy_tester_contract(web3,
                           contracts_manager,
                           deploy_contract,
                           contract_deployer_address,
                           wait_for_transaction,
                           get_random_address):
    def f(contract_name, libs=None, args=list()):
        json_contract = contracts_manager.compile_contract(contract_name, libs)
        contract = deploy_contract(
            web3,
            contract_deployer_address,
            json_contract['abi'],
            json_contract['bin'],
            args
        )
        return contract
    return f


@pytest.fixture
def token_network_contract(
    deploy_tester_contract,
    secret_registry_contract,
    standard_token_contract
):
    return deploy_tester_contract(
        'TokenNetwork',
        {
            'Token': standard_token_contract.address.encode(),
            'SecretRegistry': secret_registry_contract.address.encode()
        },
        [standard_token_contract.address, secret_registry_contract.address]
    )


@pytest.fixture
def secret_registry_contract(deploy_tester_contract):
    return deploy_tester_contract('SecretRegistry')


@pytest.fixture
def standard_token_contract(deploy_tester_contract):
    return deploy_tester_contract('HumanStandardToken', [], [1000000, 10, 'TT', 'TTK'])


@pytest.fixture
def utils_contract(deploy_tester_contract):
    return deploy_tester_contract('Utils')


@pytest.fixture
def token_network_registry_contract(deploy_tester_contract, secret_registry_contract, web3):
    return deploy_tester_contract(
        'TokenNetworksRegistry',
        [],
        [secret_registry_contract.address, int(web3.version.network)]
    )


@pytest.fixture
def token_network_registry_address(token_network_registry_contract):
    return token_network_registry_contract.address


@pytest.fixture
def standard_token_network_contract(
    web3,
    contracts_manager,
    wait_for_transaction,
    token_network_registry_contract,
    standard_token_contract,
    contract_deployer_address
):
    txid = token_network_registry_contract.transact(
        {'from': contract_deployer_address}
    ).createERC20TokenNetwork(
        standard_token_contract.address
    )
    tx_receipt = wait_for_transaction(txid)
    assert len(tx_receipt['logs']) == 1
    event_abi = get_event_from_abi(
        token_network_registry_contract.abi,
        'TokenNetworkCreated'
    )
    decoded_event = get_event_data(event_abi, tx_receipt['logs'][0])
    assert decoded_event is not None
    assert is_address(decoded_event['args']['token_address'])
    assert is_address(decoded_event['args']['token_network_address'])
    token_network_address = decoded_event['args']['token_network_address']
    token_network_abi = contracts_manager.get_contract_abi('TokenNetwork')
    return web3.eth.contract(abi=token_network_abi, address=token_network_address)

import pytest
import logging
from web3.utils.events import get_event_data
from eth_utils import is_address

log = logging.getLogger(__name__)


@pytest.fixture
def contracts_manager():
    """Reimplement this - fixture should return raiden-lib's contract manager.
        (return ContractManager(CONTRACTS_SOURCE_DIRS))"""
    raise NotImplementedError(
        'In order to use contract fixtures please override contracts_manager fixture.'
    )


@pytest.fixture
def contract_deployer_address(faucet_address) -> str:
    """Reimplement this - fixture should return an address of the account
    that has enough eth to deploy the contracts."""
    raise NotImplementedError(
        'Address of a deployer account must be overriden.'
    )


@pytest.fixture
def deploy_tester_contract(
        web3,
        contracts_manager,
        deploy_contract,
        contract_deployer_address,
        wait_for_transaction,
        get_random_address
):
    """Returns a function that can be used to deploy a named contract,
    using conract manager to compile the bytecode and get the ABI"""
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
    network_id = int(secret_registry_contract.web3.version.network)
    return deploy_tester_contract(
        'TokenNetwork',
        {
            'Token': standard_token_contract.address.encode(),
            'SecretRegistry': secret_registry_contract.address.encode()
        },
        [standard_token_contract.address, secret_registry_contract.address, network_id]
    )


@pytest.fixture
def secret_registry_contract(deploy_tester_contract):
    """Deployed SecretRegistry contract"""
    return deploy_tester_contract('SecretRegistry')


@pytest.fixture
def deploy_token_contract(deploy_tester_contract):
    """Returns a function that deploys a generic token contract"""
    def f(initial_amount: int, decimals: int, token_name: str, token_symbol: str):
        assert initial_amount > 0
        assert decimals > 0
        return deploy_tester_contract(
            'HumanStandardToken',
            [],
            [initial_amount, decimals, token_name, token_symbol]
        )

    return f


@pytest.fixture
def standard_token_contract(deploy_token_contract):
    """Deployed HumanStandardToken contract"""
    return deploy_token_contract(1000000, 10, 'TT', 'TTK')


@pytest.fixture
def utils_contract(deploy_tester_contract):
    """Deployed Utils contract"""
    return deploy_tester_contract('Utils')


@pytest.fixture
def token_network_registry_contract(deploy_tester_contract, secret_registry_contract, web3):
    """Deployed TokenNetworksRegistry contract"""
    return deploy_tester_contract(
        'TokenNetworksRegistry',
        [],
        [secret_registry_contract.address, int(web3.version.network)]
    )


@pytest.fixture
def token_network_registry_address(token_network_registry_contract):
    """Address of TokenNetworksRegistry contract"""
    return token_network_registry_contract.address


@pytest.fixture
def add_and_register_token(
        web3,
        wait_for_transaction,
        token_network_registry_contract,
        deploy_token_contract,
        contract_deployer_address,
        contracts_manager
):
    """Deploy a token and register it in TokenNetworksRegistry"""
    def f(initial_amount: int, decimals: int, token_name: str, token_symbol: str):
        token_contract = deploy_token_contract(initial_amount, decimals, token_name, token_symbol)
        txid = token_network_registry_contract.functions.createERC20TokenNetwork(
            token_contract.address
        ).transact({'from': contract_deployer_address})
        tx_receipt = wait_for_transaction(txid)
        assert len(tx_receipt['logs']) == 1
        event_abi = contracts_manager.get_event_abi(
            'TokenNetworksRegistry',
            'TokenNetworkCreated'
        )
        decoded_event = get_event_data(event_abi, tx_receipt['logs'][0])
        assert decoded_event is not None
        assert is_address(decoded_event['args']['token_address'])
        assert is_address(decoded_event['args']['token_network_address'])
        token_network_address = decoded_event['args']['token_network_address']
        token_network_abi = contracts_manager.get_contract_abi('TokenNetwork')
        return web3.eth.contract(abi=token_network_abi, address=token_network_address)

    return f


@pytest.fixture
def standard_token_network_contract(
        web3,
        contracts_manager,
        wait_for_transaction,
        token_network_registry_contract,
        standard_token_contract,
        contract_deployer_address
):
    """Return instance of a deployed TokenNetwork for HumanStandardToken."""
    txid = token_network_registry_contract.functions.createERC20TokenNetwork(
        standard_token_contract.address
    ).transact({'from': contract_deployer_address})
    tx_receipt = wait_for_transaction(txid)
    assert len(tx_receipt['logs']) == 1
    event_abi = contracts_manager.get_event_abi(
        'TokenNetworksRegistry',
        'TokenNetworkCreated'
    )
    decoded_event = get_event_data(event_abi, tx_receipt['logs'][0])
    assert decoded_event is not None
    assert is_address(decoded_event['args']['token_address'])
    assert is_address(decoded_event['args']['token_network_address'])
    token_network_address = decoded_event['args']['token_network_address']
    token_network_abi = contracts_manager.get_contract_abi('TokenNetwork')
    return web3.eth.contract(abi=token_network_abi, address=token_network_address)

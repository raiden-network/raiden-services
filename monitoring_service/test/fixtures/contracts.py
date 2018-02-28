import pytest
import os
import logging
from ethereum.tools import _solidity

from monitoring_service.config import CONTRACTS_DIR

log = logging.getLogger(__name__)


def get_contract(contract_name):
    return [
        os.path.join(CONTRACTS_DIR, x)
        for x in os.listdir(CONTRACTS_DIR)
        if os.path.basename(x).split('.', 1)[0] == contract_name
    ]


def compile_contract(contract_name, libs=None, *args):
    return _solidity.compile_contract(
        get_contract(contract_name)[0],
        contract_name,
        combined='abi,bin',
        libraries=libs
    )
#    return [
#        v for k, v in json.loads(output.decode())['contracts'].items()
#        if k.split(':', 1)[1] == contract_name
#    ]


@pytest.fixture
def get_contract_abi(json_contract_abi):
    def f(contract_name):
        return [
            v for k, v in json_contract_abi['contracts'].items()
            if k.split(':', 1)[1] == contract_name
        ]
    return f


@pytest.fixture
def contract_deployer_address(faucet_address):
    return faucet_address


@pytest.fixture
def deploy_tester_contract(web3,
                           deploy_contract,
                           contract_deployer_address,
                           wait_for_transaction,
                           get_random_address):
    def f(contract_name, libs=None, args=list()):
        json_contract = compile_contract(contract_name, libs)
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
def netting_channel_library_contract(deploy_tester_contract):
    return deploy_tester_contract('NettingChannelLibrary')


@pytest.fixture
def endpoint_registry_contract(deploy_tester_contract):
    return deploy_tester_contract('EndpointRegistry')


@pytest.fixture
def netting_channel_contract(deploy_tester_contract,
                             netting_channel_library_contract,
                             standard_token_contract,
                             get_random_address):
    libs = {'NettingChannelLibrary': netting_channel_library_contract.address.encode()}
    tk, p1, p2 = standard_token_contract.address, get_random_address(), get_random_address()
    return deploy_tester_contract('NettingChannelContract', libs, [tk, p1, p2, 20])


@pytest.fixture
def standard_token_contract(deploy_tester_contract):
    return deploy_tester_contract('HumanStandardToken', [], [1000000, 'TT', 10, 'TTK'])


@pytest.fixture
def utils_contract(deploy_tester_contract):
    return deploy_tester_contract('Utils')


@pytest.fixture
def channel_manager_library_contract(
    deploy_tester_contract,
    netting_channel_library_contract
):
    libs = {'NettingChannelLibrary': netting_channel_library_contract.address.encode()}
    return deploy_tester_contract('ChannelManagerLibrary', libs)


@pytest.fixture
def channel_manager_contract(deploy_tester_contract,
                             channel_manager_library_contract,
                             utils_contract,
                             standard_token_contract
                             ):
    libs = {
        'ChannelManagerLibrary': channel_manager_library_contract.address.encode(),
        'Utils': utils_contract.address.encode()
    }
    return deploy_tester_contract('ChannelManagerContract',
                                  libs,
                                  [standard_token_contract.address])

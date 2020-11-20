from typing import Callable

import gevent
from web3 import Web3
from web3.contract import Contract

from raiden.utils.typing import BlockNumber
from raiden_contracts.constants import CONTRACT_SERVICE_REGISTRY
from raiden_contracts.tests.utils.constants import DEFAULT_REGISTRATION_DURATION
from raiden_libs.service_registry import info, register_account, withdraw
from src.raiden_libs.utils import private_key_to_address


def test_registration(
    web3: Web3,
    service_registry: Contract,
    get_accounts: Callable,
    get_private_key: Callable,
    wait_for_blocks: Callable,
) -> None:
    """
    Test a whole registration life cycle:

    * register
    * info
    * extend
    * info
    * withdraw
    * info
    """
    (account,) = get_accounts(1)
    pk1 = get_private_key(account)
    addr1 = private_key_to_address(pk1)

    assert service_registry.functions.hasValidRegistration(account).call() is False
    assert service_registry.functions.urls(account).call() == ""

    def create_blocks():
        while True:
            wait_for_blocks(1)
            gevent.idle()

    block_creator = gevent.spawn(create_blocks)

    # register
    register_account(
        private_key=pk1,
        web3=web3,
        contracts={CONTRACT_SERVICE_REGISTRY: service_registry},
        start_block=BlockNumber(0),
        service_url="http://test",
        accept_disclaimer=True,
        accept_all=True,
    )

    # check that registration worked
    assert service_registry.functions.hasValidRegistration(account).call() is True
    assert service_registry.functions.urls(account).call() == "http://test"

    # extend registration
    register_account(
        private_key=pk1,
        web3=web3,
        contracts={CONTRACT_SERVICE_REGISTRY: service_registry},
        start_block=BlockNumber(0),
        service_url=None,
        accept_disclaimer=True,
        accept_all=True,
        extend=True,
    )

    # smoke test info command
    info(
        private_key=pk1,
        web3=web3,
        contracts={CONTRACT_SERVICE_REGISTRY: service_registry},
        start_block=BlockNumber(0),
    )

    # wait until first deposit is free
    web3.testing.timeTravel(  # type: ignore
        web3.eth.getBlock("latest")["timestamp"] + DEFAULT_REGISTRATION_DURATION
    )
    # now test withdraw
    withdraw(
        private_key=pk1,
        web3=web3,
        contracts={CONTRACT_SERVICE_REGISTRY: service_registry},
        start_block=BlockNumber(0),
        to=addr1,
    )

    # smoke test info command again after withdraw
    info(
        private_key=pk1,
        web3=web3,
        contracts={CONTRACT_SERVICE_REGISTRY: service_registry},
        start_block=BlockNumber(0),
    )

    block_creator.kill()

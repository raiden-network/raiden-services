from typing import Callable

import gevent
from web3 import Web3
from web3.contract import Contract

from raiden.utils.typing import BlockNumber
from raiden_contracts.constants import CONTRACT_SERVICE_REGISTRY
from raiden_libs.service_registry import register_account


def test_registration(
    web3: Web3,
    service_registry: Contract,
    get_accounts: Callable,
    get_private_key: Callable,
    wait_for_blocks: Callable,
) -> None:
    (account,) = get_accounts(1)
    pk1 = get_private_key(account)

    assert service_registry.functions.hasValidRegistration(account).call() is False
    assert service_registry.functions.urls(account).call() == ""

    def create_blocks():
        while True:
            wait_for_blocks(1)
            gevent.idle()

    block_creator = gevent.spawn(create_blocks)
    register_account(
        private_key=pk1,
        web3=web3,
        contracts={CONTRACT_SERVICE_REGISTRY: service_registry},
        start_block=BlockNumber(0),
        service_url="test",
        accept_disclaimer=True,
        accept_all=True,
    )

    block_creator.kill()

    # check that registration worked
    assert service_registry.functions.hasValidRegistration(account).call() is True
    assert service_registry.functions.urls(account).call() == "test"

from eth_utils import decode_hex

from raiden.utils.typing import Address, TokenAmount
from raiden_libs.register_service import deposit_to_registry, update_service_url


def test_register_mints_tokens_and_deposits(
    web3, service_registry, user_deposit_contract, get_accounts
):
    account = decode_hex(get_accounts(1)[0])
    deposit_amount = TokenAmount(100)

    deposit_to_registry(
        web3=web3,
        service_registry_contract=service_registry,
        user_deposit_contract=user_deposit_contract,
        deposit=deposit_amount,
        service_address=Address(account),
    )

    assert service_registry.functions.deposits(account).call() == deposit_amount
    assert service_registry.functions.urls(account).call() == ""


def test_update_url_set_new_url(web3, service_registry, user_deposit_contract, get_accounts):
    account = decode_hex(get_accounts(1)[0])
    deposit_amount = TokenAmount(100)

    deposit_to_registry(
        web3=web3,
        service_registry_contract=service_registry,
        user_deposit_contract=user_deposit_contract,
        deposit=deposit_amount,
        service_address=Address(account),
    )
    assert service_registry.functions.urls(account).call() == ""

    update_service_url(
        web3=web3,
        service_registry_contract=service_registry,
        service_address=Address(account),
        service_url="abc",
        current_url="",
    )
    assert service_registry.functions.urls(account).call() == "abc"

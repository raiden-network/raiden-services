import sys
from typing import Dict

import click
import structlog
from eth_utils import to_checksum_address, to_hex
from web3 import Web3
from web3.contract import Contract, ContractFunction
from web3.middleware import construct_sign_and_send_raw_middleware

from raiden.utils.typing import Address, BlockNumber
from raiden_contracts.constants import (
    CONTRACT_CUSTOM_TOKEN,
    CONTRACT_SERVICE_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_libs.cli import blockchain_options, common_options
from raiden_libs.contract_info import CONTRACT_MANAGER
from raiden_libs.utils import private_key_to_address

log = structlog.get_logger(__name__)


def checked_transact(
    web3: Web3, service_address: Address, function_call: ContractFunction, task_name: str
) -> None:
    log.info(f"Starting: {task_name}")
    transaction_hash = function_call.transact({"from": service_address})
    transaction_receipt = web3.eth.waitForTransactionReceipt(transaction_hash)
    was_successful = transaction_receipt["status"] == 1

    if not was_successful:
        log.error(
            f"Failed: {task_name}\nPlease check that the account "
            f"{to_checksum_address(service_address)} has sufficient funds.",
            receipt=transaction_receipt,
        )
        sys.exit(1)

    log.info(
        f"Finished: {task_name}",
        successful=was_successful,
        transaction_hash=to_hex(transaction_hash),
    )


@blockchain_options(contracts=[CONTRACT_SERVICE_REGISTRY, CONTRACT_USER_DEPOSIT])
@click.command()
@click.option("--service-url", type=str, help="URL for the services to register")
@common_options("register_service")
def main(
    private_key: str,
    state_db: str,  # pylint: disable=unused-argument
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,  # pylint: disable=unused-argument
    service_url: str,
) -> None:
    """
    Registers the address of a service deployment with the `ServiceRegistry`.

    The address that is registered is derived from the supplied private key.
    It also sets or updates the URL of the services deployment.
    """
    # Add middleware to sign transactions by default
    web3.middleware_stack.add(construct_sign_and_send_raw_middleware(private_key))

    service_address = private_key_to_address(private_key)
    log.info("Running service registration script", account_address=service_address)

    service_registry_contract = contracts[CONTRACT_SERVICE_REGISTRY]

    # check if already registered
    currently_registered = service_registry_contract.functions.hasValidRegistration(
        service_address
    ).call()
    current_url = service_registry_contract.functions.urls(service_address).call()
    log.info(
        "Current ServiceRegistry information for service address",
        service_address=service_address,
        currently_registered=currently_registered,
        current_url=current_url,
    )

    # Register if not yet done
    if not currently_registered:
        deposit_to_registry(
            web3=web3,
            service_registry_contract=service_registry_contract,
            user_deposit_contract=contracts[CONTRACT_USER_DEPOSIT],
            service_address=service_address,
        )

    update_service_url(
        web3=web3,
        service_registry_contract=service_registry_contract,
        service_address=service_address,
        service_url=service_url,
        current_url=current_url,
    )

    current_deposit = service_registry_contract.functions.deposits(service_address).call()
    current_url = service_registry_contract.functions.urls(service_address).call()

    log.info("Updated infos", current_deposit=current_deposit, current_url=current_url)


def deposit_to_registry(
    web3: Web3,
    service_registry_contract: Contract,
    user_deposit_contract: Contract,
    service_address: Address,
) -> None:
    log.info("Address not registered in ServiceRegistry")
    deposit_token_address = user_deposit_contract.functions.token().call()
    deposit_token_contract = web3.eth.contract(
        address=deposit_token_address, abi=CONTRACT_MANAGER.get_contract_abi(CONTRACT_CUSTOM_TOKEN)
    )

    # Get required deposit
    required_deposit = service_registry_contract.functions.currentPrice().call()

    # Check current token balance
    account_balance = deposit_token_contract.functions.balanceOf(service_address).call()
    log.info("Current account balance", balance=account_balance, required_deposit=required_deposit)

    # mint tokens if necessary
    if account_balance < required_deposit:
        checked_transact(
            web3=web3,
            service_address=service_address,
            function_call=deposit_token_contract.functions.mint(required_deposit),
            task_name="Minting new Test RDN tokens",
        )

        account_balance = deposit_token_contract.functions.balanceOf(service_address).call()
        log.info(
            "Updated account balance", balance=account_balance, desired_deposit=required_deposit
        )

    # Approve token transfer
    checked_transact(
        web3=web3,
        service_address=service_address,
        function_call=deposit_token_contract.functions.approve(
            service_registry_contract.address, required_deposit
        ),
        task_name="Allowing token transfor for deposit",
    )

    # Deposit tokens
    checked_transact(
        web3=web3,
        service_address=service_address,
        function_call=service_registry_contract.functions.deposit(required_deposit),
        task_name="Depositing to service registry",
    )


def update_service_url(
    web3: Web3,
    service_registry_contract: Contract,
    service_address: Address,
    service_url: str,
    current_url: str,
) -> None:
    # TODO: maybe check that the address is pingable
    if service_url and service_url != current_url:
        checked_transact(
            web3=web3,
            service_address=service_address,
            function_call=service_registry_contract.functions.setURL(service_url),
            task_name="Registering new URL",
        )


if __name__ == "__main__":
    main(auto_envvar_prefix="RDN_REGISTRY")  # pragma: no cover

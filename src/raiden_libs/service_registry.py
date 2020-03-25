import sys
import time
from datetime import datetime
from typing import Dict, Optional

import click
import structlog
from eth_utils import to_canonical_address, to_checksum_address, to_hex
from web3 import Web3
from web3.contract import Contract, ContractFunction
from web3.middleware import construct_sign_and_send_raw_middleware

from raiden.utils.typing import Address, BlockNumber
from raiden_contracts.constants import (
    CONTRACT_CUSTOM_TOKEN,
    CONTRACT_DEPOSIT,
    CONTRACT_SERVICE_REGISTRY,
)
from raiden_libs.blockchain import get_web3_provider_info
from raiden_libs.cli import blockchain_options, common_options, validate_address
from raiden_libs.contract_info import CONTRACT_MANAGER
from raiden_libs.utils import private_key_to_address

log = structlog.get_logger(__name__)


def checked_transact(
    web3: Web3, sender_address: Address, function_call: ContractFunction, task_name: str
) -> None:
    log.info(f"Starting: {task_name}")
    transaction_hash = function_call.transact({"from": sender_address})
    transaction_receipt = web3.eth.waitForTransactionReceipt(transaction_hash)
    was_successful = transaction_receipt["status"] == 1

    if not was_successful:
        log.error(
            f"Failed: {task_name}\nPlease check that the account "
            f"{to_checksum_address(sender_address)} has sufficient funds.",
            receipt=transaction_receipt,
        )
        sys.exit(1)

    log.info(
        f"Finished: {task_name}",
        successful=was_successful,
        transaction_hash=to_hex(transaction_hash),
    )


@click.group()
def cli() -> None:
    pass


@blockchain_options(contracts=[CONTRACT_SERVICE_REGISTRY])
@cli.command()
@click.option("--service-url", type=str, help="URL for the services to register")
@common_options("service_registry")
def register(
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
    log.info("Using RPC endpoint", rpc_url=get_web3_provider_info(web3))
    hex_addresses = {
        name: to_checksum_address(contract.address) for name, contract in contracts.items()
    }
    log.info("Contract information", addresses=hex_addresses, start_block=start_block)

    # Add middleware to sign transactions by default
    web3.middleware_onion.add(construct_sign_and_send_raw_middleware(private_key))

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
            service_address=service_address,
        )

    update_service_url(
        web3=web3,
        service_registry_contract=service_registry_contract,
        service_address=service_address,
        service_url=service_url,
        current_url=current_url,
    )

    current_url = service_registry_contract.functions.urls(service_address).call()

    log.info("Updated infos", current_url=current_url)


def deposit_to_registry(
    web3: Web3, service_registry_contract: Contract, service_address: Address,
) -> None:
    log.info("Address not registered in ServiceRegistry")
    deposit_token_address = service_registry_contract.functions.token().call()
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
            sender_address=service_address,
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
        sender_address=service_address,
        function_call=deposit_token_contract.functions.approve(
            service_registry_contract.address, required_deposit
        ),
        task_name="Allowing token transfer for deposit",
    )

    # Deposit tokens
    checked_transact(
        web3=web3,
        sender_address=service_address,
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
            sender_address=service_address,
            function_call=service_registry_contract.functions.setURL(service_url),
            task_name="Registering new URL",
        )


@blockchain_options(contracts=[CONTRACT_DEPOSIT])
@cli.command("withdraw")
@click.option(
    "--to", type=str, callback=validate_address, help="Target address for withdrawn tokens"
)
@common_options("service_registry")
def withdraw(
    private_key: str,
    state_db: str,  # pylint: disable=unused-argument
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,  # pylint: disable=unused-argument
    to: Optional[Address],
) -> None:
    """
    Withdraw tokens deposited to the ServiceRegistry.
    """
    # Add middleware to sign transactions by default
    web3.middleware_onion.add(construct_sign_and_send_raw_middleware(private_key))

    log.info("Using RPC endpoint", rpc_url=get_web3_provider_info(web3))
    deposit_contract = contracts[CONTRACT_DEPOSIT]

    # Check usage of correct key
    withdrawer = deposit_contract.functions.withdrawer().call()
    caller_address = private_key_to_address(private_key)
    if to_canonical_address(withdrawer) != caller_address:
        log.error(
            "You must used the key used to deposit when withdrawing",
            expected=withdrawer,
            actual=to_checksum_address(caller_address),
        )
        sys.exit(1)

    # Can we withdraw already?
    release_at = deposit_contract.functions.release_at().call()
    if time.time() < release_at:
        log.error(
            "Too early to withdraw",
            released_at_utc=datetime.utcfromtimestamp(release_at).isoformat(),
        )
        sys.exit(1)

    receiver = to or private_key_to_address(private_key)
    checked_transact(
        web3=web3,
        sender_address=caller_address,
        function_call=deposit_contract.functions.withdraw(receiver),
        task_name="withdraw",
    )


def main() -> None:
    cli(auto_envvar_prefix="SR")  # for ServiceRegistry


if __name__ == "__main__":
    main()  # pragma: no cover

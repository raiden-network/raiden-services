# pylint: disable=too-many-arguments,too-many-locals,too-many-statements
import subprocess
import sys
import textwrap
from datetime import datetime
from math import floor, log10
from typing import Any, Callable, Dict, List, Optional

import click
import gevent
import structlog
from eth_typing import HexStr
from eth_utils import event_abi_to_log_topic, to_canonical_address, to_checksum_address, to_hex
from hexbytes import HexBytes
from web3 import Web3
from web3.contract import Contract, ContractFunction
from web3.logs import DISCARD
from web3.middleware import construct_sign_and_send_raw_middleware
from web3.types import FilterParams, TxReceipt

from raiden.blockchain.filters import decode_event
from raiden.settings import DEFAULT_NUMBER_OF_BLOCK_CONFIRMATIONS
from raiden.utils.typing import Address, BlockNumber
from raiden_contracts.constants import (
    CONTRACT_CUSTOM_TOKEN,
    CONTRACT_DEPOSIT,
    CONTRACT_SERVICE_REGISTRY,
    EVENT_REGISTERED_SERVICE,
)
from raiden_libs.blockchain import get_web3_provider_info
from raiden_libs.cli import blockchain_options, common_options, validate_address
from raiden_libs.constants import CONFIRMATION_OF_UNDERSTANDING
from raiden_libs.contract_info import CONTRACT_MANAGER
from raiden_libs.utils import private_key_to_address

log = structlog.get_logger(__name__)


# Subdomains must include trailing dot
CHAINID_TO_ETHERSCAN_PREFIX = {
    1: "",
    3: "ropsten.",
    4: "rinkeby.",
    5: "goerli.",
    42: "kovan.",
    61: "eth-tester",
}

DISCLAIMER = textwrap.dedent(
    """\
        +------------------------------------------------------------------------+
        | This script will help you to register at the Raiden Service Registry,  |
        | see https://raiden-network-specification.readthedocs.io/en/latest/     |
        | Service Contracts for more information.                                |
        |                                                                        |
        | This is an Alpha version of experimental open source software released |
        | as a test version under an MIT license and may contain errors and/or   |
        | bugs. No guarantee or representation whatsoever is made regarding its  |
        | suitability (or its use) for any purpose or regarding its compliance   |
        | with any applicable laws and regulations. Use of the software is at    |
        | your own risk and discretion and by using the software you warrant and |
        | represent that you have read this disclaimer, understand its contents, |
        | assume all risk related thereto and hereby release, waive, discharge   |
        | and covenant not to hold liable Brainbot Labs Establishment or any of  |
        | its officers, employees or affiliates from and for any direct or       |
        | indirect damage resulting from the software or the use thereof.        |
        | Such to the extent as permissible by applicable laws and regulations.  |
        +------------------------------------------------------------------------+
    """
)


def validate_url(_ctx: Any, _param: Any, value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not (value.startswith("http://") or value.startswith("https://")):
        raise click.BadParameter("URL needs to include http(s) protocol")
    return value


def etherscan_url_for_address(chain_id: int, address: Address) -> str:
    return (
        f"https://{CHAINID_TO_ETHERSCAN_PREFIX[chain_id]}etherscan.io"
        f"/address/{to_checksum_address(address)}"
    )


def etherscan_url_for_txhash(chain_id: int, tx_hash: HexBytes) -> str:
    return f"https://{CHAINID_TO_ETHERSCAN_PREFIX[chain_id]}etherscan.io/tx/{tx_hash.hex()}"


def checked_transact(
    web3: Web3,
    sender_address: Address,
    function_call: ContractFunction,
    task_name: str,
    wait_confirmation_interval: bool = True,
) -> TxReceipt:

    log.info(f"Starting: {task_name}")
    transaction_hash = function_call.transact({"from": sender_address})

    confirmation_msg = ""
    if wait_confirmation_interval:
        confirmation_msg = " and waiting for confirmation"
    click.secho(
        f"\nSending transaction{confirmation_msg}: {task_name}"
        f"\n\tSee {etherscan_url_for_txhash(web3.eth.chainId, transaction_hash)}"
    )

    transaction_receipt = web3.eth.waitForTransactionReceipt(transaction_hash, poll_latency=1.0)
    if wait_confirmation_interval:
        while (
            "blockNumber" not in transaction_receipt
            or web3.eth.blockNumber
            < transaction_receipt["blockNumber"] + DEFAULT_NUMBER_OF_BLOCK_CONFIRMATIONS
        ):
            transaction_receipt = web3.eth.waitForTransactionReceipt(transaction_hash)
            gevent.sleep(1)

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

    return transaction_receipt


@click.group()
def cli() -> None:
    pass


@blockchain_options(contracts=[CONTRACT_SERVICE_REGISTRY])
@cli.command()
@click.option(
    "--accept-disclaimer",
    type=bool,
    default=False,
    help="Bypass the experimental software disclaimer prompt",
    is_flag=True,
)
@click.option(
    "--accept-all",
    type=bool,
    default=False,
    help="Bypass all questions (Not recommended)",
    is_flag=True,
    hidden=True,
)
@click.option(
    "--service-url", type=str, help="URL for the services to register", callback=validate_url
)
@common_options("service_registry")
def register(
    private_key: str,
    state_db: str,  # pylint: disable=unused-argument
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,  # pylint: disable=unused-argument
    service_url: Optional[str],
    accept_disclaimer: bool,
    accept_all: bool,
) -> None:
    """
    Registers the address of a service deployment with the `ServiceRegistry`.

    The address that is registered is derived from the supplied private key.
    It also sets or updates the URL of the services deployment.
    """
    register_account(
        private_key=private_key,
        web3=web3,
        contracts=contracts,
        start_block=start_block,
        service_url=service_url,
        accept_disclaimer=accept_disclaimer,
        accept_all=accept_all,
    )


def get_token_formatter(
    token_contract: Contract, min_sig_figures: int = 3
) -> Callable[[float], str]:
    """
    Return a function to nicely format token amounts.

    It will round to full tokens according to the decimal definition in the
    token contract, but it will show at least `min_sig_figures` significant
    figures. This ensures that small token amount stay readable and won't get
    rounded to zero.
    """
    symbol = token_contract.functions.symbol().call()
    decimals = token_contract.functions.decimals().call()

    def format_token_amount(amount: float) -> str:
        if amount == 0:
            return f"0 {symbol}"
        amount /= 10 ** decimals
        show_dec = max(-floor(log10(abs(amount)) + 1) + min_sig_figures, 0)
        return ("{:." + str(show_dec) + "f} {}").format(amount, symbol)

    return format_token_amount


def send_registration_transaction(
    web3: Web3,
    service_registry_contract: Contract,
    deposit_token_contract: Contract,
    maybe_prompt: Callable,
    account_balance: int,
    service_address: Address,
    fmt_amount: Callable[[float], str],
) -> None:
    # Get required deposit
    required_deposit = service_registry_contract.functions.currentPrice().call()
    click.secho(
        f"\nThe current required deposit is {fmt_amount(required_deposit)}"
        "\n\tNote: The required deposit continuously decreases, but "
        "\n\t      increases significantly after a deposit is made."
    )
    if account_balance < required_deposit:
        if web3.eth.chainId == 1:
            click.secho(
                f"You have {fmt_amount(account_balance)} but need {fmt_amount(required_deposit)}.",
                err=True,
            )
            sys.exit(1)
        else:
            click.secho("You are operating on a testnet. Tokens will be minted as required.")

    maybe_prompt(
        "I have read the current deposit and understand that continuing will transfer tokens"
    )

    # Check if the approved value is different from zero, if so reset
    # See https://github.com/raiden-network/raiden-services/issues/769
    old_allowance = deposit_token_contract.functions.allowance(
        service_address, service_registry_contract.address
    ).call()

    if old_allowance > 0:
        log.info("Found old allowance, resetting to zero", old_allowance=old_allowance)
        checked_transact(
            web3=web3,
            sender_address=service_address,
            function_call=deposit_token_contract.functions.approve(
                service_registry_contract.address, 0
            ),
            task_name="Resetting token allowance",
        )

    # Get required deposit
    latest_deposit = service_registry_contract.functions.currentPrice().call()

    # Check if required deposit increased, if so abort. Lower price is fine.
    if latest_deposit > required_deposit:
        # Not nice, but simple for now
        click.secho("The required deposit increased, please restart the registration.")
        sys.exit(1)

    # mint tokens if necessary, but only on testnets
    if account_balance < latest_deposit and web3.eth.chainId != 1:
        checked_transact(
            web3=web3,
            sender_address=service_address,
            function_call=deposit_token_contract.functions.mint(latest_deposit),
            task_name="Minting new Test RDN tokens",
        )

        balance = deposit_token_contract.functions.balanceOf(service_address).call()
        log.info(
            "Updated account balance",
            balance=balance,
            desired_deposit=latest_deposit,
        )

    # Approve token transfer
    checked_transact(
        web3=web3,
        sender_address=service_address,
        function_call=deposit_token_contract.functions.approve(
            service_registry_contract.address, latest_deposit
        ),
        task_name="Allowing token transfer for deposit",
    )

    # Deposit tokens
    receipt = checked_transact(
        web3=web3,
        sender_address=service_address,
        function_call=service_registry_contract.functions.deposit(latest_deposit),
        task_name="Depositing to service registry",
    )

    events = service_registry_contract.events.RegisteredService().processReceipt(
        receipt, errors=DISCARD
    )
    assert len(events) == 1
    event_args = events[0]["args"]
    valid_until = datetime.utcfromtimestamp(event_args["valid_till"])

    click.secho("\nSuccessfully deposited to service registry", fg="green")
    click.secho(
        f"\n\tDeposit contract address: {to_checksum_address(event_args['deposit_contract'])}"
        f"\n\t\tSee {etherscan_url_for_address(web3.eth.chainId, event_args['deposit_contract'])}"
        f"\n\tDeposit amount: {event_args['deposit_amount']}"
        f"\n\tRegistration valid until: {valid_until.isoformat(timespec='minutes')}"
    )


# Separate function to make testing easier
def register_account(
    private_key: str,
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,
    service_url: Optional[str],
    accept_disclaimer: bool,
    accept_all: bool,
    extend: bool = False,
) -> None:
    click.secho(DISCLAIMER, fg="yellow")
    if not accept_disclaimer and not accept_all:
        click.confirm(CONFIRMATION_OF_UNDERSTANDING, abort=True)

    def maybe_prompt(query: str) -> None:
        if not accept_all:
            click.confirm(query, abort=True)

    chain_id = web3.eth.chainId
    log.info("Using RPC endpoint", rpc_url=get_web3_provider_info(web3))
    hex_addresses = {
        name: to_checksum_address(contract.address) for name, contract in contracts.items()
    }
    log.info("Contract information", addresses=hex_addresses, start_block=start_block)

    # Add middleware to sign transactions by default
    web3.middleware_onion.add(construct_sign_and_send_raw_middleware(private_key))

    service_address = private_key_to_address(private_key)
    log.info("Running service registration script", account_address=service_address)
    click.secho(
        f"\nThis will run the registration with the address {to_checksum_address(service_address)}"
        f"\n\tSee {etherscan_url_for_address(chain_id, service_address)}"
    )
    maybe_prompt("I have checked that the address is correct and want to continue")

    # Create contract proxies
    service_registry_contract = contracts[CONTRACT_SERVICE_REGISTRY]
    service_registry_address = to_canonical_address(service_registry_contract.address)
    deposit_token_address = service_registry_contract.functions.token().call()
    deposit_token_contract = web3.eth.contract(
        address=deposit_token_address,
        abi=CONTRACT_MANAGER.get_contract_abi(CONTRACT_CUSTOM_TOKEN),
    )

    click.secho(
        "\nThe address of the service registry contract used is "
        f"{to_checksum_address(service_registry_contract.address)}"
        f"\n\tSee {etherscan_url_for_address(chain_id, service_registry_address)}"
    )
    maybe_prompt("I have checked that the address is correct and want to continue")

    # Check current token balance
    fmt_amount = get_token_formatter(deposit_token_contract)
    account_balance = deposit_token_contract.functions.balanceOf(service_address).call()
    log.info("Current account balance", balance=account_balance)
    click.secho(
        "\nThe address of the token used is "
        f"{to_checksum_address(deposit_token_address)}"
        f"\n\tSee {etherscan_url_for_address(chain_id, deposit_token_address)}"
        f"\nThe account balance of that token is {fmt_amount(account_balance)}."
    )
    maybe_prompt("I have checked that the address and my balance are correct and want to continue")

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

    # Register if not yet done or extension is requested
    if extend and currently_registered:
        log.info("Registration found. Preparing to extend registration.")
        send_registration_transaction(
            web3=web3,
            service_registry_contract=service_registry_contract,
            deposit_token_contract=deposit_token_contract,
            maybe_prompt=maybe_prompt,
            account_balance=account_balance,
            service_address=service_address,
            fmt_amount=fmt_amount,
        )
    elif not currently_registered:
        log.info("Address not registered in ServiceRegistry")
        send_registration_transaction(
            web3=web3,
            service_registry_contract=service_registry_contract,
            deposit_token_contract=deposit_token_contract,
            maybe_prompt=maybe_prompt,
            account_balance=account_balance,
            service_address=service_address,
            fmt_amount=fmt_amount,
        )
    else:
        log.info(
            "Already registered. If you want to extend your registration, "
            "use the 'extend' command."
        )

    if service_url and service_url != current_url:
        click.secho(f'\nNew Url to be registered "{service_url}"')
        hostname = service_url.split("//")[1]
        reachable = not subprocess.run(
            ["ping", "-c", "1", hostname], capture_output=True, check=False
        ).returncode
        if not reachable:
            click.secho(f"`ping {hostname}` fails. Are you sure the URL is correct?", fg="yellow")
        maybe_prompt("I have checked the URL and it is correct")

        checked_transact(
            web3=web3,
            sender_address=service_address,
            function_call=service_registry_contract.functions.setURL(service_url),
            task_name="Registering new URL",
        )

    current_url = service_registry_contract.functions.urls(service_address).call()

    click.secho("\nThank you for registering your services!", fg="green")
    log.info("Updated infos", current_url=current_url)


def find_deposits(
    web3: Web3,
    service_address: Address,
    service_registry_contract: Contract,
    start_block: BlockNumber,
) -> List[Dict[str, Any]]:
    """
    Return the address of the oldest deposit contract which is not withdrawn
    """
    # Get RegisteredService events for service_address
    event_abi = dict(service_registry_contract.events[EVENT_REGISTERED_SERVICE]().abi)
    topics = [
        event_abi_to_log_topic(event_abi),
        bytes([0] * 12) + service_address,
    ]
    filter_params = FilterParams(
        {
            "fromBlock": start_block,
            "toBlock": "latest",
            "address": service_registry_contract.address,
            "topics": [HexStr("0x" + t.hex()) for t in topics],
        }
    )
    raw_events = web3.eth.getLogs(filter_params)
    events = [decode_event(service_registry_contract.abi, event) for event in raw_events]

    # Bring events into a pleasant form
    return [
        dict(
            block_number=e["blockNumber"],
            valid_till=datetime.utcfromtimestamp(e["args"]["valid_till"]).isoformat(" "),
            amount=e["args"]["deposit_amount"],
            deposit_contract=e["args"]["deposit_contract"],
            withdrawn=not web3.eth.getCode(e["args"]["deposit_contract"]),
        )
        for e in events
    ]


def find_withdrawable_deposit(
    web3: Web3,
    service_address: Address,
    service_registry_contract: Contract,
    start_block: BlockNumber,
) -> Address:
    # Get formatter for token amounts
    deposit_token_address = service_registry_contract.functions.token().call()
    deposit_token_contract = web3.eth.contract(
        address=deposit_token_address,
        abi=CONTRACT_MANAGER.get_contract_abi(CONTRACT_CUSTOM_TOKEN),
    )
    fmt_amount = get_token_formatter(deposit_token_contract)

    # Find deposits
    deposits = find_deposits(web3, service_address, service_registry_contract, start_block)
    deposits = [d for d in deposits if not d["withdrawn"]]
    if not deposits:
        click.echo("No deposits found!", err=True)
        sys.exit(1)

    # Inform user
    print("Deposit found:")
    for deposit_event in deposits:
        valid_till = deposit_event["valid_till"]
        amount = deposit_event["amount"]
        print(f" * valid till {valid_till}, amount: {fmt_amount(amount)}")
    if len(deposits) > 1:
        print("I will withdraw the first (oldest) one. Run this script again for the next deposit")

    return to_canonical_address(deposits[0]["deposit_contract"])


def withdraw(
    private_key: str,
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,
    to: Optional[Address],
) -> None:
    log.info("Using RPC endpoint", rpc_url=get_web3_provider_info(web3))
    service_registry_contract = contracts[CONTRACT_SERVICE_REGISTRY]
    caller_address = private_key_to_address(private_key)

    # Find deposit contract address
    caller_address = private_key_to_address(private_key)
    deposit_contract_address = find_withdrawable_deposit(
        web3=web3,
        service_address=caller_address,
        service_registry_contract=service_registry_contract,
        start_block=start_block,
    )
    deposit_contract = web3.eth.contract(
        abi=CONTRACT_MANAGER.get_contract_abi(CONTRACT_DEPOSIT), address=deposit_contract_address
    )

    # Check usage of correct key
    withdrawer = deposit_contract.functions.withdrawer().call()
    if to_canonical_address(withdrawer) != caller_address:
        log.error(
            "You must use the key used to deposit when withdrawing",
            expected=withdrawer,
            actual=to_checksum_address(caller_address),
        )
        sys.exit(1)

    # Can we withdraw already?
    release_at = deposit_contract.functions.release_at().call()
    deprecated = service_registry_contract.functions.deprecated().call()
    if web3.eth.getBlock("latest")["timestamp"] < release_at and not deprecated:
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
        wait_confirmation_interval=False,
    )


@blockchain_options(contracts=[CONTRACT_SERVICE_REGISTRY])
@cli.command("withdraw")
@click.option(
    "--to",
    type=str,
    callback=validate_address,
    help="Target address for withdrawn tokens",
)
@common_options("service_registry")
def withdraw_cmd(
    private_key: str,
    state_db: str,  # pylint: disable=unused-argument
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,
    to: Optional[Address],
) -> None:
    """
    Withdraw tokens deposited to the ServiceRegistry.
    """
    # Add middleware to sign transactions by default
    web3.middleware_onion.add(construct_sign_and_send_raw_middleware(private_key))

    withdraw(private_key, web3, contracts, start_block, to)


def info(
    private_key: str,
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,
) -> None:
    log.info("Using RPC endpoint", rpc_url=get_web3_provider_info(web3))
    service_registry_contract = contracts[CONTRACT_SERVICE_REGISTRY]
    deposit_token_address = service_registry_contract.functions.token().call()
    deposit_token_contract = web3.eth.contract(
        address=deposit_token_address,
        abi=CONTRACT_MANAGER.get_contract_abi(CONTRACT_CUSTOM_TOKEN),
    )
    caller_address = private_key_to_address(private_key)
    fmt_amount = get_token_formatter(deposit_token_contract)

    deposits = find_deposits(
        web3=web3,
        service_address=caller_address,
        service_registry_contract=service_registry_contract,
        start_block=start_block,
    )
    if not deposits:
        print("No deposits were made from this account.")
        return

    print("Deposits:")
    for dep in deposits:
        print(f" * block {dep['block_number']}", end=", ")
        print(f"amount: {fmt_amount(dep['amount'])}", end=", ")
        if dep["withdrawn"]:
            print("WITHDRAWN")
        else:
            print("increased validity till " + dep["valid_till"])


@blockchain_options(contracts=[CONTRACT_SERVICE_REGISTRY])
@cli.command("info")
@common_options("service_registry")
def info_cmd(
    private_key: str,
    state_db: str,  # pylint: disable=unused-argument
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,
) -> None:
    """
    Show information about current registration and deposits
    """
    info(private_key, web3, contracts, start_block)


@blockchain_options(contracts=[CONTRACT_SERVICE_REGISTRY])
@cli.command("extend")
@click.option(
    "--accept-disclaimer",
    type=bool,
    default=False,
    help="Bypass the experimental software disclaimer prompt",
    is_flag=True,
)
@click.option(
    "--accept-all",
    type=bool,
    default=False,
    help="Bypass all questions (Not recommended)",
    is_flag=True,
    hidden=True,
)
@common_options("service_registry")
def extend_cmd(
    private_key: str,
    state_db: str,  # pylint: disable=unused-argument
    web3: Web3,
    contracts: Dict[str, Contract],
    start_block: BlockNumber,
    accept_disclaimer: bool,
    accept_all: bool,
) -> None:
    """
    Extend the duration of a service registration
    """
    register_account(
        private_key=private_key,
        web3=web3,
        contracts=contracts,
        start_block=start_block,
        service_url=None,
        accept_disclaimer=accept_disclaimer,
        accept_all=accept_all,
        extend=True,
    )


def main() -> None:
    cli(auto_envvar_prefix="SR")  # for ServiceRegistry


if __name__ == "__main__":
    main()  # pragma: no cover

import datetime
import json
import logging
import os
import sys
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple

import click
import gevent
import pkg_resources
import requests.exceptions
import sentry_sdk
import structlog
from eth_account import Account
from eth_typing import URI
from eth_utils import is_checksum_address, to_canonical_address
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from web3 import HTTPProvider, Web3
from web3.contract import Contract
from web3.middleware import geth_poa_middleware, simple_cache_middleware
from web3.types import Wei

from pathfinding_service.middleware import http_retry_with_backoff_middleware
from raiden.utils.cli import EnumChoiceType, GasPriceChoiceType
from raiden.utils.typing import Address, BlockNumber, ChainID
from raiden_contracts.constants import (
    CONTRACT_DEPOSIT,
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_ONE_TO_N,
    CONTRACT_SERVICE_REGISTRY,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
    CONTRACTS_VERSION,
)
from raiden_contracts.contract_manager import ContractDevEnvironment
from raiden_contracts.utils.type_aliases import PrivateKey
from raiden_libs.contract_info import CONTRACT_MANAGER, get_contract_addresses_and_start_block
from raiden_libs.logging import setup_logging

log = structlog.get_logger(__name__)


def _open_keystore(keystore_file: str, password: str) -> PrivateKey:
    with open(keystore_file, "r") as keystore:
        try:
            private_key = bytes(
                Account.decrypt(keyfile_json=json.load(keystore), password=password)
            )
            return PrivateKey(private_key)
        except ValueError as error:
            log.critical(
                "Could not decode keyfile with given password. Please try again.",
                reason=str(error),
            )
            sys.exit(1)


def validate_address(
    _ctx: click.Context, _param: click.Parameter, value: Optional[str]
) -> Optional[Address]:
    if value is None:
        # None as default value allowed
        return None
    if not is_checksum_address(value):
        raise click.BadParameter("not an EIP-55 checksummed address")
    return to_canonical_address(value)


def start_profiler(output_dir: Optional[str]) -> Optional[Any]:
    """Start and return a profiler is `output_dir` is not None"""
    if not output_dir:
        return None

    from raiden.utils.profiling.sampler import FlameGraphCollector, SignalSampler

    os.makedirs(output_dir, exist_ok=True)
    now = datetime.datetime.now()
    stack_path = os.path.join(output_dir, f"{now:%Y%m%d_%H%M}_stack.data")
    stack_stream = open(stack_path, "w")  # pylint: disable=consider-using-with
    flame = FlameGraphCollector(stack_stream)
    return SignalSampler(flame)


def common_options(app_name: str) -> Callable:
    """A decorator to be used with all service commands

    It will pass new args to the given func:
    * private_key (as a result of `--keystore-file` and `--password`)
    * state_db
    * log_level
    * log_json

    The `app_name` will be used to determine the state_db location.
    """

    def decorator(func: Callable) -> Callable:
        for option in reversed(
            [
                click.option(
                    "--keystore-file",
                    required=True,
                    type=click.Path(exists=True, dir_okay=False, readable=True),
                    help="Path to a keystore file.",
                ),
                click.password_option(
                    "--password",
                    confirmation_prompt=False,
                    help="Password to unlock the keystore file.",
                ),
                click.option(
                    "--state-db",
                    type=str,
                    help="Path to SQLite3 db which stores the application state",
                ),
                click.option(
                    "--log-level",
                    default="INFO",
                    type=click.Choice(["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]),
                    help="Print log messages of this level and more important ones",
                ),
                click.option(
                    "--log-json/--no-log-json",
                    default=False,
                    help="Enable or disable logging in JSON format",
                ),
                click.option(
                    "--flamegraph",
                    help="Directory in which to save a stack profile to produce flame graphs.",
                    type=click.Path(
                        exists=False,
                        dir_okay=True,
                        file_okay=False,
                        writable=True,
                        resolve_path=True,
                        allow_dash=False,
                    ),
                    default=None,
                ),
            ]
        ):
            func = option(func)

        @wraps(func)
        def call_with_common_options_initialized(**params: Any) -> Callable:
            profiler = start_profiler(params.pop("flamegraph"))

            params["private_key"] = _open_keystore(
                params.pop("keystore_file"), params.pop("password")
            )

            # Don't print traceback on KeyboardInterrupt
            gevent.get_hub().NOT_ERROR += (KeyboardInterrupt,)

            try:
                setup_logging(log_level=params.pop("log_level"), log_json=params.pop("log_json"))
                if not params["state_db"]:
                    # only RC has `chain_id`, MS and PFS have `web3` object
                    chain_id = str(params.get("chain_id") or params["web3"].net.version)
                    contracts_version = CONTRACTS_VERSION.replace(".", "_")
                    filename = f"{app_name}-{chain_id}-{contracts_version}.db"
                    data_dir = click.get_app_dir(app_name)
                    params["state_db"] = os.path.join(data_dir, filename)

                # Need to delete the `chain_id` key
                if params.get("chain_id") is not None:
                    del params["chain_id"]

                return func(**params)
            finally:
                if profiler:
                    profiler.stop()
                structlog.reset_defaults()

        return call_with_common_options_initialized

    return decorator


def blockchain_options(contracts: List[str]) -> Callable:
    """A decorator providing blockchain related params to a command"""
    options = [
        click.Option(
            ["--eth-rpc"], default="http://localhost:8545", type=str, help="Ethereum node RPC URI"
        ),
        click.Option(
            ["--gas-price"],
            help=(
                "Set the gas price for ethereum transactions. If not provided "
                "the 'normal' gas price startegy is used.\n"
                "Available options:\n"
                '"fast" - transactions are usually mined within 60 seconds\n'
                '"normal" - transactions are usually mined within 5 minutes\n'
                "<GAS_PRICE> - use given gas price\n"
            ),
            type=GasPriceChoiceType(["normal", "fast"]),
            default="fast",
            show_default=True,
        ),
        click.Option(
            ["--development-environment"],
            help=(
                "Choose which set of services and transport servers should be used. "
                "Change this only when you are developing Raiden itself."
            ),
            type=EnumChoiceType(ContractDevEnvironment),
            default=ContractDevEnvironment.DEMO.value,
        ),
    ]

    arg_for_contract = {
        CONTRACT_TOKEN_NETWORK_REGISTRY: "token-network-registry-contract",
        CONTRACT_USER_DEPOSIT: "user-deposit-contract",
        CONTRACT_MONITORING_SERVICE: "monitor-contract",
        CONTRACT_ONE_TO_N: "one-to-n-contract",
        CONTRACT_SERVICE_REGISTRY: "service-registry-contract",
        CONTRACT_DEPOSIT: "service-deposit-contract",
    }
    address_required = {CONTRACT_DEPOSIT}

    param_for_contract: Dict[str, str] = {}
    for con in contracts:
        option = click.Option(
            ["--{}-address".format(arg_for_contract[con])],
            type=str,
            help=f"Address of the {con} contract",
            callback=validate_address,
            required=con in address_required,
        )
        options.append(option)
        param_for_contract[con] = option.human_readable_name

    def decorator(command: click.Command) -> click.Command:
        assert command.callback
        callback = command.callback

        command.params += options

        def call_with_blockchain_info(**params: Any) -> Callable:
            address_overwrites = {
                contract: value
                for contract, value in (
                    (contract, params.pop(param)) for contract, param in param_for_contract.items()
                )
                if value is not None
            }
            params["web3"], params["contracts"], params["start_block"] = connect_to_blockchain(
                eth_rpc=params.pop("eth_rpc"),
                gas_price_strategy=params.pop("gas_price"),
                used_contracts=contracts,
                address_overwrites=address_overwrites,
                development_environment=params.pop("development_environment"),
            )
            return callback(**params)

        command.callback = call_with_blockchain_info
        return command

    return decorator


def connect_to_blockchain(
    eth_rpc: URI,
    gas_price_strategy: Callable[[Web3, Any], Wei],
    used_contracts: List[str],
    address_overwrites: Dict[str, Address],
    development_environment: ContractDevEnvironment,
) -> Tuple[Web3, Dict[str, Contract], BlockNumber]:
    try:
        provider = HTTPProvider(eth_rpc)
        web3 = Web3(provider)
        # Will throw ConnectionError on bad Ethereum client
        chain_id = ChainID(web3.eth.chainId)
    except requests.exceptions.ConnectionError:
        log.error(
            "Can not connect to the Ethereum client. Please check that it is running and that "
            "your settings are correct.",
            eth_rpc=eth_rpc,
        )
        sys.exit(1)

    # Add POA middleware for geth POA chains, no/op for other chains
    web3.middleware_onion.inject(geth_poa_middleware, layer=0)

    # Set gas price strategy
    # for that we also need a cache middleware, otherwise sampling is expensive
    web3.middleware_onion.add(simple_cache_middleware)
    web3.eth.setGasPriceStrategy(gas_price_strategy)

    # give web3 some time between retries before failing
    # TODO: find a way to to this type safe
    provider.middlewares.replace(  # type: ignore
        "http_retry_request", http_retry_with_backoff_middleware
    )

    addresses, start_block = get_contract_addresses_and_start_block(
        chain_id=chain_id,
        contracts=used_contracts,
        address_overwrites=address_overwrites,
        development_environment=development_environment,
    )
    contracts = {
        c: web3.eth.contract(abi=CONTRACT_MANAGER.get_contract_abi(c), address=address)
        for c, address in addresses.items()
    }

    return web3, contracts, start_block


def setup_sentry(enable_flask_integration: bool = False) -> None:
    logging.logThreads = False
    sentry_dsn = os.environ.get("SENTRY_DSN")
    environment = os.environ.get("DEPLOY_ENV")
    if sentry_dsn is not None:
        log.info("Initializing sentry", dsn=sentry_dsn)
        integrations: List[Any] = [LoggingIntegration(level=logging.INFO, event_level=None)]
        if enable_flask_integration:
            integrations.append(FlaskIntegration())
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=integrations,
            release=pkg_resources.get_distribution("raiden-services").version,
            environment=environment,
        )

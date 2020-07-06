# pylint: disable=redefined-outer-name
import logging
from unittest.mock import DEFAULT, MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from pathfinding_service.cli import main
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_ONE_TO_N,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from tests.libs.mocks.web3 import Web3Mock

PATCH_ARGS = {
    "target": "pathfinding_service.cli",
    "PathfindingService": DEFAULT,
    "PFSApi": DEFAULT,
    "get_web3_provider_info": MagicMock(return_value=""),
}

PATCH_INFO_ARGS = {
    "target": "raiden_libs.cli",
    "get_contract_addresses_and_start_block": MagicMock(
        return_value=(
            {
                CONTRACT_TOKEN_NETWORK_REGISTRY: "0xde1fAa1385403f05C20a8ca5a0D5106163A35B6e",
                CONTRACT_MONITORING_SERVICE: "0x58c73CabCFB3c55B420E3F60a4b06098e9D1960E",
                CONTRACT_USER_DEPOSIT: "0x85F2c5eA50861DF5eA2EBd3651fAB091e14B849C",
                CONTRACT_ONE_TO_N: "0x1717727737777777777777777777777777777777",
            },
            5235346,
        )
    ),
}


@pytest.fixture
def provider_mock(monkeypatch):
    provider_mock = Mock()
    monkeypatch.setattr("raiden_libs.cli.HTTPProvider", provider_mock)
    web3_mock = Web3Mock()
    web3_mock.provider = provider_mock
    web3_mock.return_value.eth.contract = lambda address, **kwargs: Mock(address=address)
    monkeypatch.setattr("raiden_libs.cli.Web3", web3_mock)
    return provider_mock


def test_bad_eth_client(log, default_cli_args):
    """ Giving a bad `eth-rpc` value should yield a concise error message """
    runner = CliRunner()
    with patch("pathfinding_service.cli.PathfindingService"):
        result = runner.invoke(
            main,
            default_cli_args + ["--eth-rpc", "http://localhost:12345"],
            catch_exceptions=False,
        )
    assert result.exit_code == 1
    assert log.has(
        "Can not connect to the Ethereum client. Please check that it is running "
        "and that your settings are correct."
    )


@pytest.mark.usefixtures("provider_mock")
def test_success(default_cli_args):
    """ Calling the pathfinding_service with default args should succeed after heavy mocking """
    runner = CliRunner()
    with patch.multiple(**PATCH_ARGS), patch.multiple(**PATCH_INFO_ARGS):  # type: ignore
        result = runner.invoke(main, default_cli_args, catch_exceptions=False)
    assert result.exit_code == 0


def test_eth_rpc(default_cli_args, provider_mock):
    """ The `eth-rpc` parameter must reach the `HTTPProvider` """
    runner = CliRunner()
    eth_rpc = "example.com:1234"
    with patch.multiple(**PATCH_ARGS), patch.multiple(**PATCH_INFO_ARGS):  # type: ignore
        runner.invoke(main, default_cli_args + ["--eth-rpc", eth_rpc])
    provider_mock.assert_called_with(eth_rpc)


@pytest.mark.usefixtures("provider_mock")
def test_registry_address(default_cli_args):
    runner = CliRunner()

    # check validation of address format
    def fails_on_registry_check(address):
        result = runner.invoke(
            main,
            default_cli_args + ["--token-network-registry-contract-address", address],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "EIP-55" in result.output

    fails_on_registry_check("1" * 40)  # no 0x
    fails_on_registry_check("0x" + "1" * 41)  # not 40 digits
    fails_on_registry_check("0x" + "1" * 39)  # not 40 digits


@pytest.mark.usefixtures("provider_mock")
def test_confirmations(default_cli_args):
    """ The `confirmations` parameter must reach the `PathfindingService` """
    runner = CliRunner()
    with patch.multiple(**PATCH_ARGS) as mocks, patch.multiple(**PATCH_INFO_ARGS):  # type: ignore
        confirmations = 77
        result = runner.invoke(
            main,
            default_cli_args + ["--confirmations", str(confirmations)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert mocks["PathfindingService"].call_args[1]["required_confirmations"] == confirmations


@pytest.mark.usefixtures("provider_mock")
def test_shutdown(default_cli_args):
    """ Clean shutdown after KeyboardInterrupt """
    runner = CliRunner()
    with patch.multiple(**PATCH_ARGS) as mocks, patch.multiple(**PATCH_INFO_ARGS):  # type: ignore
        mocks["PathfindingService"].return_value.get.side_effect = KeyboardInterrupt
        result = runner.invoke(main, default_cli_args, catch_exceptions=False)
        assert result.exit_code == 0
        assert "Exiting" in result.output
        assert mocks["PathfindingService"].return_value.stop.called
        assert mocks["PFSApi"].return_value.stop.called


@pytest.mark.usefixtures("provider_mock")
def test_log_level(default_cli_args):
    """ Setting of log level via command line switch """
    runner = CliRunner()
    with patch.multiple(**PATCH_ARGS), patch.multiple(**PATCH_INFO_ARGS), patch(  # type: ignore
        "logging.basicConfig"
    ) as basic_config:
        for log_level in ("CRITICAL", "WARNING"):
            result = runner.invoke(
                main, default_cli_args + ["--log-level", log_level], catch_exceptions=False
            )
            assert result.exit_code == 0
            # pytest already initializes logging, so basicConfig does not have
            # an effect. Use mocking to check that it's called properly.
            assert logging.getLevelName(basic_config.call_args[1]["level"] == log_level)

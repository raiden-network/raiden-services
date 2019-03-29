import logging
from unittest.mock import DEFAULT, MagicMock, patch

from click.testing import CliRunner
from eth_utils import to_checksum_address

from pathfinding_service.cli import main
from raiden_contracts.constants import (
    CONTRACT_MONITORING_SERVICE,
    CONTRACT_TOKEN_NETWORK_REGISTRY,
    CONTRACT_USER_DEPOSIT,
)
from raiden_libs.contract_info import START_BLOCK_ID

patch_args = {
    'target': 'pathfinding_service.cli',
    'PathfindingService': DEFAULT,
    'ServiceApi': DEFAULT,
    'HTTPProvider': DEFAULT,
}

patch_info_args = {
    'target': 'raiden_libs.contract_info',
    'get_deployment_infos': MagicMock(return_value={
        CONTRACT_TOKEN_NETWORK_REGISTRY: '0xde1fAa1385403f05C20a8ca5a0D5106163A35B6e',
        CONTRACT_MONITORING_SERVICE: '0x58c73CabCFB3c55B420E3F60a4b06098e9D1960E',
        CONTRACT_USER_DEPOSIT: '0x85F2c5eA50861DF5eA2EBd3651fAB091e14B849C',
        START_BLOCK_ID: 5235346,
    }),
}


def test_bad_eth_client(log, default_cli_args):
    """ Giving a bad `eth-rpc` value should yield a concise error message """
    runner = CliRunner()
    with patch('pathfinding_service.cli.PathfindingService'):
        result = runner.invoke(
            main,
            default_cli_args + ['--eth-rpc', 'http://localhost:12345'],
            catch_exceptions=False,
        )
    assert result.exit_code == 1
    assert log.has(
        'Can not connect to the Ethereum client. Please check that it is running '
        'and that your settings are correct.',
    )


def test_success(default_cli_args):
    """ Calling the pathfinding_service with default args should succeed after heavy mocking """
    runner = CliRunner()
    with patch.multiple(**patch_args), patch.multiple(**patch_info_args):
        result = runner.invoke(
            main,
            default_cli_args,
        )
    assert result.exit_code == 0


def test_eth_rpc(default_cli_args):
    """ The `eth-rpc` parameter must reach the `HTTPProvider` """
    runner = CliRunner()
    eth_rpc = 'example.com:1234'
    with patch('pathfinding_service.cli.HTTPProvider') as provider:
        runner.invoke(
            main,
            default_cli_args + ['--eth-rpc', eth_rpc],
        )
        provider.assert_called_with(eth_rpc)


def test_registry_address(default_cli_args):
    """ The `registry_address` parameter must reach the `PathfindingService` """
    runner = CliRunner()
    with patch.multiple(**patch_args) as mocks, patch.multiple(**patch_info_args):
        address = to_checksum_address('0x' + '1' * 40)
        result = runner.invoke(
            main,
            default_cli_args + ['--registry-address', address],
        )
        assert result.exit_code == 0
        assert mocks['PathfindingService'].call_args[1]['registry_address'] == address

    # check validation of address format
    def fails_on_registry_check(address):
        result = runner.invoke(
            main,
            default_cli_args + ['--registry-address', address],
            catch_exceptions=False)
        assert result.exit_code != 0
        assert 'EIP-55' in result.output

    fails_on_registry_check('1' * 40)  # no 0x
    fails_on_registry_check('0x' + '1' * 41)  # not 40 digits
    fails_on_registry_check('0x' + '1' * 39)  # not 40 digits


def test_start_block(default_cli_args):
    """ The `start_block` parameter must reach the `PathfindingService`

    We also have to pass a registry address, because `start_block` is
    overwritten with a default when no registry has been specified.
    """
    runner = CliRunner()
    with patch.multiple(**patch_args) as mocks, patch.multiple(**patch_info_args):
        start_block = 10
        address = to_checksum_address('0x' + '1' * 40)
        address2 = to_checksum_address('0x' + '2' * 40)
        result = runner.invoke(
            main,
            default_cli_args + [
                '--registry-address', address,
                '--user-deposit-contract-address', address2,
                '--start-block', str(start_block)],
        )
        assert result.exit_code == 0
        assert mocks['PathfindingService'].call_args[1]['sync_start_block'] == start_block


def test_confirmations(default_cli_args):
    """ The `confirmations` parameter must reach the `PathfindingService` """
    runner = CliRunner()
    with patch.multiple(**patch_args) as mocks, patch.multiple(**patch_info_args):
        confirmations = 77
        result = runner.invoke(
            main,
            default_cli_args + [
                '--confirmations', str(confirmations)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert mocks['PathfindingService'].call_args[1]['required_confirmations'] == confirmations


def test_shutdown(default_cli_args):
    """ Clean shutdown after KeyboardInterrupt """
    runner = CliRunner()
    with patch.multiple(**patch_args) as mocks, patch.multiple(**patch_info_args):
        mocks['PathfindingService'].return_value.run.side_effect = KeyboardInterrupt
        result = runner.invoke(
            main,
            default_cli_args,
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert 'Exiting' in result.output
        assert mocks['PathfindingService'].return_value.stop.called
        assert mocks['ServiceApi'].return_value.stop.called


def test_log_level(default_cli_args):
    """ Setting of log level via command line switch """
    runner = CliRunner()
    with patch.multiple(**patch_args), patch('logging.basicConfig') as basicConfig:
        for log_level in ('CRITICAL', 'WARNING'):
            runner.invoke(
                main,
                default_cli_args + ['--log-level', log_level],
            )
            # pytest already initializes logging, so basicConfig does not have
            # an effect. Use mocking to check that it's called properly.
            assert logging.getLevelName(
                basicConfig.call_args[1]['level'] == log_level,
            )

import logging
from unittest.mock import DEFAULT, patch

from click.testing import CliRunner
from eth_utils import to_checksum_address

from monitoring_service.cli import main

DEFAULT_ARGS = [
    '--private-key', 'some_key',
    '--matrix-username', 'TEST',
    '--matrix-password', 'TEST',
]

patch_args = dict(
    target='monitoring_service.cli',
    MonitoringService=DEFAULT,
    HTTPProvider=DEFAULT,
)


def test_bad_eth_client(caplog):
    """ Giving a bad `eth-rpc` value should yield a concise error message """
    runner = CliRunner()
    result = runner.invoke(main, DEFAULT_ARGS + ['--eth-rpc', 'http://localhost:12345'])
    assert result.exit_code == 1
    assert 'Can not connect to the Ethereum client' in caplog.text


def test_success():
    """ Calling the monitoring_service with default args should succeed after heavy mocking """
    runner = CliRunner()
    with patch.multiple(**patch_args):
        result = runner.invoke(main, DEFAULT_ARGS)
    assert result.exit_code == 0


def test_eth_rpc():
    """ The `eth-rpc` parameter must reach the `HTTPProvider` """
    runner = CliRunner()
    eth_rpc = 'example.com:1234'
    with patch('monitoring_service.cli.HTTPProvider') as provider:
        runner.invoke(main, DEFAULT_ARGS + ['--eth-rpc', eth_rpc])
        provider.assert_called_with(eth_rpc)


def test_registry_address():
    """ The `registry_address` parameter must reach the `MonitoringService` """
    runner = CliRunner()
    with patch.multiple(**patch_args) as mocks:
        address = to_checksum_address('0x' + '1' * 40)
        result = runner.invoke(main, DEFAULT_ARGS + ['--registry-address', address])
        assert result.exit_code == 0
        assert mocks['MonitoringService'].call_args[1]['registry_address'] == address

    # check validation of address format
    def fails_on_registry_check(address):
        result = runner.invoke(main, ['--registry-address', address], catch_exceptions=False)
        assert result.exit_code != 0
        assert 'EIP-55' in result.output

    fails_on_registry_check('1' * 40)  # no 0x
    fails_on_registry_check('0x' + '1' * 41)  # not 40 digits
    fails_on_registry_check('0x' + '1' * 39)  # not 40 digits


def test_shutdown():
    """ Clean shutdown after KeyboardInterrupt """
    runner = CliRunner()
    with patch.multiple(**patch_args) as mocks:
        mocks['MonitoringService'].return_value.run.side_effect = KeyboardInterrupt
        result = runner.invoke(main, DEFAULT_ARGS, catch_exceptions=False)
        assert result.exit_code == 0
        assert 'Exiting' in result.output
        assert mocks['MonitoringService'].return_value.stop.called


def test_log_level():
    """ Setting of log level via command line switch """
    runner = CliRunner()
    with patch('monitoring_service.cli.logging.basicConfig') as basicConfig:
        for log_level in ('CRITICAL', 'WARNING'):
            runner.invoke(main, DEFAULT_ARGS + ['--log-level', log_level])
            # pytest already initializes logging, so basicConfig does not have
            # an effect. Use mocking to check that it's called properly.
            assert logging.getLevelName(
                basicConfig.call_args[1]['level'] == log_level,
            )

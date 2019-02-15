import logging
from unittest.mock import DEFAULT, patch

from click.testing import CliRunner

from monitoring_service.cli import main

patch_args = dict(
    target='monitoring_service.cli',
    MonitoringService=DEFAULT,
    HTTPProvider=DEFAULT,
)


def test_success(keystore_file, default_cli_args):
    """ Calling the monitoring_service with default args should succeed after heavy mocking """
    runner = CliRunner()
    with patch.multiple(**patch_args):
        result = runner.invoke(
            main,
            default_cli_args,
            catch_exceptions=False,
        )
    assert result.exit_code == 0


def test_wrong_password(keystore_file, default_cli_args):
    """ Calling the monitoring_service with default args should succeed after heavy mocking """
    runner = CliRunner()
    with patch.multiple(**patch_args):
        result = runner.invoke(
            main,
            default_cli_args + ['--password', 'wrong'],
            catch_exceptions=False,
        )
    assert result.exit_code == 1


def test_shutdown(keystore_file, default_cli_args):
    """ Clean shutdown after KeyboardInterrupt """
    runner = CliRunner()
    with patch.multiple(**patch_args) as mocks:
        mocks['MonitoringService'].return_value.run.side_effect = KeyboardInterrupt
        result = runner.invoke(
            main,
            default_cli_args,
            catch_exceptions=False,
        )
        assert result.exit_code == 0


def test_log_level(keystore_file, default_cli_args):
    """ Setting of log level via command line switch """
    runner = CliRunner()
    with patch.multiple(**patch_args), \
            patch('request_collector.cli.logging.basicConfig') as basicConfig:
        for log_level in ('CRITICAL', 'WARNING'):
            runner.invoke(
                main,
                default_cli_args + ['--log-level', log_level],
                catch_exceptions=False,
            )
            # pytest already initializes logging, so basicConfig does not have
            # an effect. Use mocking to check that it's called properly.
            assert logging.getLevelName(
                basicConfig.call_args[1]['level'] == log_level,
            )

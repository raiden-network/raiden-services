import logging
from unittest.mock import DEFAULT, patch

from click.testing import CliRunner
from request_collector.cli import main

PATCH_ARGS = dict(target="request_collector.cli", RequestCollector=DEFAULT)


def test_success(default_cli_args):
    """Calling the request_collector with default args should succeed after heavy mocking"""
    runner = CliRunner()
    with patch.multiple(**PATCH_ARGS):
        result = runner.invoke(
            main, default_cli_args + ["--chain-id", "mainnet"], catch_exceptions=False
        )
    assert result.exit_code == 0


def test_wrong_password(default_cli_args):
    """Calling the request_collector with default args should succeed after heavy mocking"""
    runner = CliRunner()
    with patch.multiple(**PATCH_ARGS):
        result = runner.invoke(
            main,
            default_cli_args + ["--chain-id", "mainnet", "--password", "wrong"],
            catch_exceptions=False,
        )
    assert result.exit_code == 1


def test_shutdown(default_cli_args):
    """Clean shutdown after KeyboardInterrupt"""
    runner = CliRunner()
    with patch.multiple(**PATCH_ARGS) as mocks:
        mocks["RequestCollector"].return_value.run.side_effect = KeyboardInterrupt
        result = runner.invoke(
            main, default_cli_args + ["--chain-id", "mainnet"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "Exiting" in result.output
        assert mocks["RequestCollector"].return_value.listen_forever.called


def test_log_level(default_cli_args):
    """Setting of log level via command line switch"""
    runner = CliRunner()
    with patch.multiple(**PATCH_ARGS), patch("logging.basicConfig") as basic_config:
        for log_level in ("CRITICAL", "WARNING"):
            runner.invoke(
                main,
                default_cli_args + ["--chain-id", "mainnet", "--log-level", log_level],
                catch_exceptions=False,
            )
            # pytest already initializes logging, so basicConfig does not have
            # an effect. Use mocking to check that it's called properly.
            assert logging.getLevelName(basic_config.call_args[1]["level"] == log_level)

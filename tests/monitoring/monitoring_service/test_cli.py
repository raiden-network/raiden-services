# pylint: disable=redefined-outer-name
import logging
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from monitoring_service.cli import main
from monitoring_service.service import check_gas_reserve


@pytest.fixture(autouse=True)
def service_mock(monkeypatch):
    web3_mock = Mock(providers=[Mock()])
    connect_mock = Mock(return_value=(web3_mock, MagicMock(), Mock()))

    monkeypatch.setattr("raiden_libs.cli.connect_to_blockchain", connect_mock)
    service_mock = Mock()
    monkeypatch.setattr("monitoring_service.cli.MonitoringService", service_mock)
    return service_mock


def test_account_check(web3, capsys):
    private_key = "0F951D6EAF7685D420AACCA3900127E669892FE5CA6C8E4C572A59B0609AAE6B"
    check_gas_reserve(web3, private_key)
    out = capsys.readouterr().out
    assert "Your account's balance is below the estimated gas reserve of" in out


def test_success(default_cli_args_ms):
    """ Calling the monitoring_service with default args should succeed after heavy mocking """
    runner = CliRunner()
    result = runner.invoke(main, default_cli_args_ms, catch_exceptions=False)
    assert result.exit_code == 0


def test_wrong_password(default_cli_args_ms):
    """ Using the wrong password should fail, but not raise an exception """
    runner = CliRunner()
    result = runner.invoke(
        main, default_cli_args_ms + ["--password", "wrong"], catch_exceptions=False
    )
    assert result.exit_code == 1


def test_shutdown(default_cli_args_ms, service_mock):
    """ Clean shutdown after KeyboardInterrupt """
    runner = CliRunner()
    service_mock.return_value.run.side_effect = KeyboardInterrupt
    result = runner.invoke(main, default_cli_args_ms, catch_exceptions=False)
    assert result.exit_code == 0


def test_log_level(default_cli_args_ms):
    """ Setting of log level via command line switch """
    runner = CliRunner()
    with patch("logging.basicConfig") as basic_config:
        for log_level in ("CRITICAL", "WARNING"):
            runner.invoke(
                main, default_cli_args_ms + ["--log-level", log_level], catch_exceptions=False
            )
            # pytest already initializes logging, so basicConfig does not have
            # an effect. Use mocking to check that it's called properly.
            assert logging.getLevelName(basic_config.call_args[1]["level"] == log_level)

import logging
from unittest.mock import DEFAULT, patch

from click.testing import CliRunner
from request_collector.cli import main

DEFAULT_ARGS = [
    '--private-key', '0x' + '1' * 40,
    '--state-db', ':memory:',
]

patch_args = dict(
    target='request_collector.cli',
    RequestCollector=DEFAULT,
)


def test_success():
    """ Calling the request_collector with default args should succeed after heavy mocking """
    runner = CliRunner()
    with patch.multiple(**patch_args):
        result = runner.invoke(main, DEFAULT_ARGS, catch_exceptions=False)
    assert result.exit_code == 0


def test_shutdown():
    """ Clean shutdown after KeyboardInterrupt """
    runner = CliRunner()
    with patch.multiple(**patch_args) as mocks:
        mocks['RequestCollector'].return_value.run.side_effect = KeyboardInterrupt
        result = runner.invoke(main, DEFAULT_ARGS, catch_exceptions=False)
        assert result.exit_code == 0
        assert 'Exiting' in result.output
        assert mocks['RequestCollector'].return_value.stop.called


def test_log_level():
    """ Setting of log level via command line switch """
    runner = CliRunner()
    with patch.multiple(**patch_args), \
            patch('request_collector.cli.logging.basicConfig') as basicConfig:
        for log_level in ('CRITICAL', 'WARNING'):
            runner.invoke(main, DEFAULT_ARGS + ['--log-level', log_level], catch_exceptions=False)
            # pytest already initializes logging, so basicConfig does not have
            # an effect. Use mocking to check that it's called properly.
            assert logging.getLevelName(
                basicConfig.call_args[1]['level'] == log_level,
            )

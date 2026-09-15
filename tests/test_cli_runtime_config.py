"""CLI sub-commands that open the database check the configuration first.

``Settings.assert_runtime_ready()`` only ran when the server booted, and the
CLI never boots it: on a fresh install ``apowerb agents list`` surfaced a raw
PostgreSQL ``OperationalError`` instead of naming the missing variables
(apowerb/roadmap#44).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from apowerb.cli.main import app
from apowerb.configs.settings import RUNTIME_REQUIRED_FIELDS, get_settings

_CONFIGURED = {
    "DB_HOST": "localhost",
    "DB_NAME": "apowerb",
    "DB_USER": "apowerb",
    "DB_PASSWORD": "secret",
    "ENCRYPT_KEY": "0" * 43 + "=",
}

# Each command that reaches the database, with what it would call to get there.
_DATABASE_COMMANDS = [
    (["agents", "list"], ["apowerb.cli.agents.get_agent_store", "apowerb.cli.agents.fetch_agents"]),
    (["agents", "get", "agent1"], ["apowerb.cli.agents.get_agent"]),
    (
        ["agents", "create", "--name", "a", "--system-prompt", "p"],
        ["apowerb.cli.agents.validate_agent_model", "apowerb.cli.agents.register_agent"],
    ),
    (["agents", "delete", "agent1", "--force"], ["apowerb.cli.agents.delete_agent"]),
    (["agents", "export", "--owner", "a@example.com"], ["apowerb.core.agent_seeds.export_agents"]),
    (["agents", "import", "--dry-run"], ["apowerb.core.agent_seeds.import_agents"]),
    (["runs", "start", "agent1"], ["apowerb.cli.runs.get_agent_store", "apowerb.cli.runs.get_agent"]),
]


@pytest.fixture
def unconfigured(tmp_path, monkeypatch):
    # No .env in the working directory, no variable in the environment.
    monkeypatch.chdir(tmp_path)
    for field in RUNTIME_REQUIRED_FIELDS:
        monkeypatch.delenv(field.upper(), raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def configured(unconfigured, monkeypatch):
    for name, value in _CONFIGURED.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()


def _invoke_with_database_mocked(args, targets, **mock_kwargs):
    mocks = {target: MagicMock(**mock_kwargs) for target in targets}
    patchers = [patch(target, mock) for target, mock in mocks.items()]
    for patcher in patchers:
        patcher.start()
    try:
        return CliRunner().invoke(app, args), mocks
    finally:
        for patcher in patchers:
            patcher.stop()


@pytest.mark.parametrize(
    ("args", "targets"), _DATABASE_COMMANDS, ids=[" ".join(args) for args, _ in _DATABASE_COMMANDS]
)
def test_a_database_command_names_the_missing_variables_without_opening_the_database(
    unconfigured, args, targets
):
    result, mocks = _invoke_with_database_mocked(
        args, targets, side_effect=AssertionError("the database was reached")
    )

    assert result.exit_code == 1, result.output
    for field in RUNTIME_REQUIRED_FIELDS:
        assert field.upper() in result.output
    reached = [target for target, mock in mocks.items() if mock.called]
    assert reached == [], f"reached without configuration: {reached}"
    assert result.exception is None or isinstance(result.exception, SystemExit)


@pytest.mark.parametrize(
    "args",
    [["--help"], ["agents", "--help"], ["agents", "list", "--help"], ["runs", "start", "--help"]],
)
def test_help_works_without_configuration(unconfigured, args):
    result = CliRunner().invoke(app, args)

    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


def test_a_command_without_database_is_not_refused(unconfigured):
    result = CliRunner().invoke(app, ["runs", "status", "agent1"])

    assert result.exit_code == 0, result.output
    assert "stopped" in result.output


def test_a_configured_install_reaches_the_database(configured):
    result, mocks = _invoke_with_database_mocked(
        ["agents", "list"],
        ["apowerb.cli.agents.get_agent_store", "apowerb.cli.agents.fetch_agents"],
        return_value=[],
    )

    assert result.exit_code == 0, result.output
    assert mocks["apowerb.cli.agents.fetch_agents"].called
    assert "No agents found" in result.output

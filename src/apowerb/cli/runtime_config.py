"""Refuse a CLI command that needs the database while the configuration is incomplete.

The server calls ``Settings.assert_runtime_ready()`` when it boots. The CLI never
boots it, so on a fresh install ``apowerb agents list`` met a raw PostgreSQL
``OperationalError`` instead of the names of the missing variables
(apowerb/roadmap#44).

Called at the top of each command body rather than from a group callback: Click
runs a group callback before it parses the sub-command, so
``apowerb agents list --help`` would have been refused as well.
"""

import typer

from apowerb.configs.settings import get_settings


def require_runtime_config() -> None:
    """Exit with the missing variables named, before anything opens the database."""
    try:
        get_settings().assert_runtime_ready()
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None

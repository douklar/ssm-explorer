"""
`check` command — validate local installation, config, and AWS profile wiring.

This command is offline by default. It reads local config and botocore metadata,
but does not call AWS APIs.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import botocore.session
import click
import typer

from ssm_explorer import __version__
from ssm_explorer.config import load_config, resolve_config_path
from ssm_explorer.display import console

EXPECTED_ROOT_COMMANDS = {
    "browse",
    "check",
    "config",
    "diff",
    "export",
    "get",
    "install",
    "list",
    "search",
    "uninstall",
}

CheckStatus = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class CheckResult:
    status: CheckStatus
    name: str
    detail: str


def _display_path(path: Path) -> str:
    """Return a user-safe path for terminal output."""
    try:
        return str(path.expanduser().resolve()).replace(str(Path.home()), "~", 1)
    except RuntimeError:
        return str(path)


def _row_status(status: CheckStatus) -> str:
    if status == "pass":
        return "[bright_green]PASS[/bright_green]"
    if status == "warn":
        return "[bright_yellow]WARN[/bright_yellow]"
    return "[bright_red]FAIL[/bright_red]"


def _root_commands(ctx: typer.Context) -> set[str]:
    root = ctx.find_root()
    command = root.command
    if not isinstance(command, click.Group):
        return set()
    return set(command.list_commands(root))


def _profile_exists(profile: str, available_profiles: list[str]) -> bool:
    return profile in available_profiles


def _region_exists(region: str, available_regions: list[str]) -> bool:
    return region in available_regions


def check_command(
    ctx: typer.Context,
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="AWS named profile to validate."),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option("--region", "-r", help="AWS region to validate."),
    ] = None,
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-C", help="Path to a custom config file.", metavar="FILE"),
    ] = None,
) -> None:
    """
    Check local install, CLI command registry, config, AWS profile, and region.

    No AWS API calls are made. Use this after installing once to verify that
    `ssm-explorer` can run from any directory with your configured defaults.
    """
    results: list[CheckResult] = [
        CheckResult("pass", "version", f"ssm-explorer {__version__}"),
    ]

    exe = shutil.which("ssm-explorer")
    if exe:
        results.append(CheckResult("pass", "executable", "ssm-explorer found on PATH"))
    else:
        results.append(
            CheckResult(
                "warn",
                "executable",
                "ssm-explorer not found on PATH; install with `pipx install .` or use `poetry run`.",
            )
        )

    commands = _root_commands(ctx)
    missing_commands = sorted(EXPECTED_ROOT_COMMANDS - commands)
    if missing_commands:
        results.append(
            CheckResult(
                "fail",
                "commands",
                f"missing command(s): {', '.join(missing_commands)}",
            )
        )
    else:
        results.append(
            CheckResult(
                "pass",
                "commands",
                f"registered: {', '.join(sorted(EXPECTED_ROOT_COMMANDS))}",
            )
        )

    config_path = resolve_config_path(config_file)
    if config_path.exists():
        results.append(CheckResult("pass", "config file", _display_path(config_path)))
    else:
        results.append(
            CheckResult(
                "warn",
                "config file",
                f"{_display_path(config_path)} not found; using built-in defaults.",
            )
        )

    try:
        active = load_config(config_file)
        results.append(CheckResult("pass", "config parse", "valid TOML and settings"))
    except ValueError as exc:
        results.append(CheckResult("fail", "config parse", str(exc)))
        _print_results(results)
        raise typer.Exit(code=1) from exc

    try:
        resolved_profile, resolved_region = active.resolve_aws(profile, region)
        results.append(CheckResult("pass", "aws profile", resolved_profile))
        results.append(CheckResult("pass", "aws region", resolved_region))
    except ValueError as exc:
        results.append(CheckResult("fail", "aws defaults", str(exc)))
        _print_results(results)
        raise typer.Exit(code=1) from exc

    default_path = active.resolve_path(None, resolved_profile)
    if default_path:
        results.append(CheckResult("pass", "default path", default_path))
    else:
        results.append(
            CheckResult(
                "warn",
                "default path",
                "not set; pass PATH to list/search/export/browse/diff.",
            )
        )

    session = botocore.session.Session()
    available_profiles = session.available_profiles
    available_regions = session.get_available_regions("ssm")

    if _profile_exists(resolved_profile, available_profiles):
        results.append(
            CheckResult(
                "pass",
                "local AWS profile",
                f"'{resolved_profile}' exists in local AWS config.",
            )
        )
    else:
        results.append(
            CheckResult(
                "fail",
                "local AWS profile",
                f"'{resolved_profile}' not found in local AWS config.",
            )
        )

    if _region_exists(resolved_region, available_regions):
        results.append(
            CheckResult(
                "pass",
                "SSM region",
                f"'{resolved_region}' is a known SSM region.",
            )
        )
    else:
        results.append(
            CheckResult(
                "fail",
                "SSM region",
                f"'{resolved_region}' is not a known SSM region.",
            )
        )

    _print_results(results)
    if any(result.status == "fail" for result in results):
        raise typer.Exit(code=1)

    console.print("[bright_green]Ready:[/bright_green] install and config checks passed.")


def _print_results(results: list[CheckResult]) -> None:
    from rich import box
    from rich.table import Table

    table = Table(
        title="SSM Explorer Check",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold bright_white on #1e3a5f",
        border_style="dim #5b7fbf",
    )
    table.add_column("Status", no_wrap=True)
    table.add_column("Check", style="#d8dee9", no_wrap=True)
    table.add_column("Detail", style="bright_white")

    for result in results:
        table.add_row(_row_status(result.status), result.name, result.detail)

    console.print()
    console.print(table)
    console.print()

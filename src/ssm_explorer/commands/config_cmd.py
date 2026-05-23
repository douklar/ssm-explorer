"""
`config` command group — view, initialise, and inspect SSM Explorer configuration.

Sub-commands
------------
  ssm-explorer config show    Print the effective merged configuration.
  ssm-explorer config set     Set a configuration value and save to file.
  ssm-explorer config init    Write a default config file to disk.
  ssm-explorer config path    Print the active config file path.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ssm_explorer.config import (
    DEFAULT_CONFIG_TEMPLATE,
    AppConfig,
    load_config,
    resolve_config_path,
    save_config,
)
from ssm_explorer.display import console, print_error, print_info, print_success, print_warning

app = typer.Typer(
    name="config",
    help="View, initialise, and inspect the SSM Explorer configuration.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# `config path`
# ---------------------------------------------------------------------------


@app.command("path")
def path_command(
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Override config file path.", metavar="FILE"),
    ] = None,
) -> None:
    """Print the active config file path and whether it exists."""
    resolved = resolve_config_path(config_file)
    exists = resolved.exists()
    status = "[bright_green]✔ exists[/bright_green]" if exists else "[dim]✘ not found (using defaults)[/dim]"
    console.print(f"\n  Config file: [#d8dee9]{resolved}[/#d8dee9]  {status}\n")


# ---------------------------------------------------------------------------
# `config show`
# ---------------------------------------------------------------------------


@app.command("show")
def show_command(
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Override config file path.", metavar="FILE"),
    ] = None,
) -> None:
    """
    Display the effective configuration (merged TOML + env vars + defaults).

    Shows the exact values that will be used when you run any command.
    """
    from rich import box
    from rich.table import Table
    from rich.text import Text

    try:
        active_cfg = load_config(config_file)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    resolved = resolve_config_path(config_file)
    exists = resolved.exists()

    console.print()

    # Header
    src_line = (
        f"[#d8dee9]{resolved}[/#d8dee9]"
        if exists
        else f"[dim]{resolved}[/dim] [yellow](not found — using defaults)[/yellow]"
    )
    console.print(f"  [dim]Config source:[/dim] {src_line}")
    console.print()

    def _section_table(title: str, rows: list[tuple[str, str, str]]) -> None:
        """Render a compact section table."""
        tbl = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="bold bright_white on #1e3a5f",
            border_style="dim #5b7fbf",
            padding=(0, 2),
            title=Text(title, style="bold #5b7fbf"),
            title_justify="left",
        )
        tbl.add_column("Key", style="bright_yellow", no_wrap=True, min_width=22)
        tbl.add_column("Value", style="bright_white", min_width=30)
        tbl.add_column("Description", style="dim white")
        for key, val, desc in rows:
            tbl.add_row(key, val, desc)
        console.print(tbl)

    # ── [aws] ────────────────────────────────────────────────────────────
    _section_table(
        "[aws]",
        [
            ("profile", active_cfg.aws.profile, "AWS named profile"),
            ("region",  active_cfg.aws.region,  "AWS region"),
        ],
    )

    # ── [search] ─────────────────────────────────────────────────────────
    dp = active_cfg.search.default_path or "[dim](not set — PATH required)[/dim]"
    _section_table(
        "[search]",
        [
            ("default_path", dp,                               "Default SSM path prefix"),
            ("recursive",    str(active_cfg.search.recursive), "Recurse sub-paths"),
            ("decrypt",      str(active_cfg.search.decrypt),   "Decrypt SecureString values"),
            ("fetch_strategy", active_cfg.search.fetch_strategy, "Fetch mode (auto/path/batch)"),
            ("fetch_workers", str(active_cfg.search.fetch_workers), "Batch fetch workers"),
            ("max_get_tps", str(active_cfg.search.max_get_tps), "GetParameter(s) TPS cap"),
            ("max_describe_tps", str(active_cfg.search.max_describe_tps), "DescribeParameters TPS cap"),
        ],
    )

    # ── [display] ────────────────────────────────────────────────────────
    _section_table(
        "[display]",
        [
            ("conceal",           str(active_cfg.display.conceal),           "Conceal SecureString values"),
            ("show_arn",          str(active_cfg.display.show_arn),          "Show ARN column"),
            ("show_env_variable", str(active_cfg.display.show_env_variable), "Show ENV variable column"),
            ("show_value",        str(active_cfg.display.show_value),        "Show value column"),
            ("show_type",         str(active_cfg.display.show_type),         "Show type column"),
            ("show_full_path",    str(active_cfg.display.show_full_path),    "Show full parameter path column"),
            ("show_version",      str(active_cfg.display.show_version),      "Show version column"),
            ("show_last_modified", str(active_cfg.display.show_last_modified), "Show last modified column"),
            ("max_value_length",  str(active_cfg.display.max_value_length),  "Max chars in Value column"),
        ],
    )

    # ── [filter] ─────────────────────────────────────────────────────────
    _section_table(
        "[filter]",
        [
            ("enabled",      str(active_cfg.filter.enabled),      "Allow interactive browse command"),
            ("default_mode", active_cfg.filter.default_mode,      "Default filter mode (name/value)"),
        ],
    )

    # ── [output] ─────────────────────────────────────────────────────────
    save_val = (
        "[bright_green]true[/bright_green]"
        if active_cfg.output.save
        else "[dim]false (read-only mode)[/dim]"
    )
    out_path = active_cfg.output.path or "[dim](not set — --output-file required)[/dim]"
    _section_table(
        "[output]",
        [
            ("save",      save_val,                          "Enable file saving"),
            ("path",      out_path,                          "Default output file path"),
            ("format",    active_cfg.output.format,          "Export format (env/json)"),
            ("overwrite", str(active_cfg.output.overwrite),  "Overwrite existing files"),
        ],
    )

    # Read-only notice
    console.print(
        "  [dim]🔒 READ-ONLY mode — all AWS operations are strictly read-only "
        "(SSM read APIs only; no AWS write calls).[/dim]\n"
    )


# ---------------------------------------------------------------------------
# `config set`
# ---------------------------------------------------------------------------


@app.command("set")
def set_command(
    key: Annotated[
        str,
        typer.Argument(
            help="Config key to set, e.g. 'aws.profile' or 'output.save'",
        ),
    ],
    value: Annotated[
        str,
        typer.Argument(
            help="Value to set. 'true'/'false' are converted to booleans. Numbers to integers.",
        ),
    ],
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Override config file path.", metavar="FILE"),
    ] = None,
) -> None:
    """
    Set a configuration value and save it to the config file.

    The key must be in the format 'section.field'.

    \b
    Examples:
      ssm-explorer config set aws.profile my_profile
      ssm-explorer config set output.save true
      ssm-explorer config set display.max_value_length 100
    """
    try:
        active_cfg = load_config(config_file)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    parts = key.split(".")
    if len(parts) != 2:
        print_error(f"Invalid key format: '{key}'. Must be 'section.field' (e.g. aws.profile).")
        raise typer.Exit(code=1)

    section, field = parts

    # Convert value type based on simple heuristics
    val: bool | int | str = value
    val_lower = value.lower()
    if val_lower in ("true", "yes", "on"):
        val = True
    elif val_lower in ("false", "no", "off"):
        val = False
    elif value.isdigit():
        val = int(value)

    # Use pydantic to update and validate the config
    try:
        section_obj = getattr(active_cfg, section)
        setattr(section_obj, field, val)
        # re-validate whole config
        active_cfg = AppConfig.model_validate(active_cfg.model_dump())
    except AttributeError:
        print_error(f"Unknown config section or field: '{key}'.")
        raise typer.Exit(code=1) from None
    except ValueError as exc:
        print_error(f"Invalid value for '{key}': {exc}")
        raise typer.Exit(code=1) from None

    try:
        path = resolve_config_path(config_file)
        save_config(active_cfg, path)
    except OSError as exc:
        print_error(f"Could not save config file: {exc}")
        raise typer.Exit(code=1) from exc

    print_success(f"Config updated: {key} = {val}")
    print_info(f"Saved to: {path}")


# ---------------------------------------------------------------------------
# `config init`
# ---------------------------------------------------------------------------


@app.command("init")
def init_command(
    config_file: Annotated[
        str | None,
        typer.Option(
            "--config", "-c",
            help="Path where the config file should be written. Defaults to the standard location.",
            metavar="FILE",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force", "-f",
            help="Overwrite an existing config file.",
        ),
    ] = False,
) -> None:
    """
    Create a default config file with commented documentation.

    The generated file contains every available setting with explanations.
    Edit it to customise your defaults.

    \b
    Examples:
      ssm-explorer config init                          # writes to default location
      ssm-explorer config init --config ./my.toml      # custom path
      ssm-explorer config init --force                  # overwrite existing
    """
    target = resolve_config_path(config_file)

    if target.exists() and not force:
        print_warning(
            f"Config file already exists: {target}\n"
            "  Use --force to overwrite it."
        )
        raise typer.Exit(code=0)

    # Create parent directories if needed
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        target.chmod(0o600)
    except OSError as exc:
        print_error(f"Could not write config file: {exc}")
        raise typer.Exit(code=1) from exc

    print_success(f"Config file created: {target}")
    print_info("Edit it to customise your defaults, then run:  ssm-explorer config show")

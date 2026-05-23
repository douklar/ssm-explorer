"""
`browse` command — interactive live-filter browser for SSM parameters.

READ-ONLY: uses SSM read APIs only. No AWS writes occur.

Controls
--------
  Type          Live-filter parameters (by ENV name or value, see mode badge)
  Tab           Toggle filter mode: ENV Name ↔ Value
  ↑ / ↓        Move selection up / down
  Enter         Print selected parameter details and exit
  Esc / Ctrl+C  Exit without selection
"""

from __future__ import annotations

from typing import Annotated

import typer

from ssm_explorer.aws.ssm_client import (
    SSMAccessDeniedError,
    SSMAuthError,
    SSMClient,
    SSMClientError,
)
from ssm_explorer.commands.examples import is_example_arg, print_command_examples
from ssm_explorer.config import cfg, load_config
from ssm_explorer.display import (
    console,
    error_console,
    print_error,
    print_info,
    print_warning,
    render_json,
    render_single_parameter,
)

app = typer.Typer()


@app.command("browse")
def browse_command(
    path: Annotated[
        str | None,
        typer.Argument(
            help=(
                "SSM path prefix to browse. Falls back to search.default_path in config if omitted."
            ),
            metavar="PATH",
        ),
    ] = None,
    # ── AWS connection ──────────────────────────────────────────────────
    profile: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="AWS named profile."),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option("--region", "-r", help="AWS region."),
    ] = None,
    # ── Fetch options ───────────────────────────────────────────────────
    decrypt: Annotated[
        bool | None,
        typer.Option("--decrypt/--no-decrypt", "-d/-D", help="Decrypt SecureString values."),
    ] = None,
    recursive: Annotated[
        bool | None,
        typer.Option("--recursive/--no-recursive", help="Recurse sub-paths."),
    ] = None,
    # ── Display options ─────────────────────────────────────────────────
    conceal: Annotated[
        bool | None,
        typer.Option(
            "--conceal/--no-conceal",
            help="Conceal SecureString values in the detail view after selection.",
        ),
    ] = None,
    # ── Post-selection output ───────────────────────────────────────────
    output: Annotated[
        str,
        typer.Option(
            "--output",
            "-o",
            help="What to show after selecting: 'detail' (default), 'value', 'json'.",
            metavar="FORMAT",
        ),
    ] = "detail",
    # ── Config override ─────────────────────────────────────────────────
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-C", help="Path to a custom config file.", metavar="FILE"),
    ] = None,
) -> None:
    """
    Interactively browse and live-filter SSM parameters.

    Loads all parameters from the path, then opens a real-time TUI.
    Start typing to filter instantly. Press Tab to switch between filtering
    by ENV variable name or by value. Press Enter to inspect a parameter.

    \b
    Examples:
      ssm-explorer browse /my/path/to/var --profile my_profile_aws
      ssm-explorer browse /my/path/to/var --profile my_profile_aws --decrypt
      ssm-explorer browse --profile my_profile_aws            # uses default_path
      ssm-explorer browse /my/path --output value             # print raw value after select
    """
    if is_example_arg(path):
        print_command_examples("browse")
        return

    active = load_config(config_file) if config_file else cfg

    try:
        resolved_profile, resolved_region = active.resolve_aws(profile, region)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    defaults = active.defaults_for_profiles(resolved_profile)

    if not defaults.filter_enabled:
        print_error(
            "The interactive browser is disabled (filter.enabled = false in config).\n"
            "Set  filter.enabled = true  to enable it."
        )
        raise typer.Exit(code=1)

    resolved_path = active.resolve_path(path, resolved_profile)
    resolved_decrypt = decrypt if decrypt is not None else defaults.search.decrypt
    resolved_recurse = recursive if recursive is not None else defaults.search.recursive
    resolved_conceal = conceal if conceal is not None else defaults.display.conceal

    if not resolved_path:
        print_error(
            "No path provided. Pass PATH as an argument or set "
            "search.default_path or aws.profiles.<profile>.default_path in your config file."
        )
        raise typer.Exit(code=1)

    if not resolved_decrypt:
        print_warning("SecureString values are masked. Use --decrypt to filter/view by value.")

    # ── Load parameters from AWS (read-only) ─────────────────────────────
    try:
        client = SSMClient(
            profile=resolved_profile,
            region=resolved_region,
            fetch_workers=defaults.search.fetch_workers,
            max_get_tps=defaults.search.max_get_tps,
            max_describe_tps=defaults.search.max_describe_tps,
        )
        with error_console.status(
            f"[info]Fetching SSM parameters from {resolved_path} ({resolved_profile}, {resolved_region})...[/info]",
            spinner="dots",
        ):
            result = client.get_parameters_by_path(
                resolved_path,
                recursive=resolved_recurse,
                decrypt=resolved_decrypt,
                strategy=defaults.search.fetch_strategy,
            )
    except (SSMAuthError, SSMAccessDeniedError, SSMClientError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    if not result.parameters:
        print_info(f"No parameters found under path: {resolved_path}")
        return

    console.print(
        f"  [dim]Loaded[/dim] [bold bright_magenta]{result.total_count}[/bold bright_magenta]"
        f" [dim]parameter(s). Opening browser…[/dim]\n"
    )

    # ── Launch interactive TUI ────────────────────────────────────────────
    from ssm_explorer.display.interactive import FilterMode, run_interactive_filter

    # Respect filter.default_mode from config
    initial_mode = FilterMode.VALUE if defaults.filter.default_mode == "value" else FilterMode.NAME

    try:
        selected = run_interactive_filter(result, initial_mode=initial_mode)
    except KeyboardInterrupt:
        console.print("\n  [dim]Cancelled.[/dim]")
        raise typer.Exit(code=0) from None

    if selected is None:
        console.print("  [dim]No parameter selected. Exiting.[/dim]")
        return

    console.print()

    if output == "value":
        print(selected.display_value(decrypt=resolved_decrypt, conceal=resolved_conceal))
    elif output == "json":
        render_json(selected.to_dict(conceal=resolved_conceal))
    else:
        render_single_parameter(selected, decrypt=resolved_decrypt, conceal=resolved_conceal)

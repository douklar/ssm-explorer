"""
`search` command — search and filter SSM parameters by path and/or value.

READ-ONLY: uses SSM read APIs only. No AWS writes occur.
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
    render_header,
    render_json,
    render_parameter_table,
)

app = typer.Typer()


@app.command("search")
def search_command(
    path: Annotated[
        str | None,
        typer.Argument(
            help=(
                "SSM path prefix to search under. "
                "Falls back to search.default_path in config if omitted."
            ),
            metavar="PATH",
        ),
    ] = None,
    # ── Filters ─────────────────────────────────────────────────────────
    filter_path: Annotated[
        str | None,
        typer.Option(
            "--filter-path",
            "--filter",
            "-f",
            help="Match full parameter path/name (case-insensitive).",
            metavar="PATTERN",
        ),
    ] = None,
    filter_value: Annotated[
        str | None,
        typer.Option(
            "--filter-value",
            "-v",
            help="Match parameter value (case-insensitive).",
            metavar="PATTERN",
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
            help="Conceal SecureString values (first 4 chars + **** + char count).",
        ),
    ] = None,
    show_arn: Annotated[
        bool | None,
        typer.Option("--show-arn/--no-show-arn", help="Include ARN column."),
    ] = None,
    show_type: Annotated[
        bool | None,
        typer.Option("--show-type/--no-show-type", help="Include parameter type column."),
    ] = None,
    show_version: Annotated[
        bool | None,
        typer.Option("--show-version/--no-show-version", help="Include parameter version column."),
    ] = None,
    show_last_modified: Annotated[
        bool | None,
        typer.Option(
            "--show-last-modified/--no-show-last-modified",
            help="Include last modified date column.",
        ),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output format: 'table' or 'json'.", metavar="FORMAT"),
    ] = "table",
    # ── Config override ─────────────────────────────────────────────────
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-C", help="Path to a custom config file.", metavar="FILE"),
    ] = None,
) -> None:
    """
    Search and filter SSM parameters by path and/or value pattern.

    Loads all parameters under the path, then applies the filter(s) locally.
    At least one of --filter-path or --filter-value is recommended; without either,
    this behaves like the 'list' command.

    \b
    Examples:
      ssm-explorer search /my/path --filter-path /my/path/DATABASE --profile my_profile_aws
      ssm-explorer search /my/path --filter-value "postgres://" --profile my_profile_aws
      ssm-explorer search /my/path --filter-path /my/path/DB --filter-value "5432" --decrypt
    """
    if is_example_arg(path):
        print_command_examples("search")
        return

    active = load_config(config_file) if config_file else cfg

    try:
        resolved_profile, resolved_region = active.resolve_aws(profile, region)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    defaults = active.defaults_for_profiles(resolved_profile)
    resolved_path = active.resolve_path(path, resolved_profile)
    resolved_decrypt = decrypt if decrypt is not None else defaults.search.decrypt
    resolved_recurse = recursive if recursive is not None else defaults.search.recursive
    resolved_conceal = conceal if conceal is not None else defaults.display.conceal
    resolved_arn = show_arn if show_arn is not None else defaults.display.show_arn
    resolved_show_type = bool(show_type)
    resolved_show_version = bool(show_version)
    resolved_show_last_modified = bool(show_last_modified)

    if not resolved_path:
        print_error(
            "No path provided. Pass PATH as an argument or set "
            "search.default_path or aws.profiles.<profile>.default_path in your config file."
        )
        raise typer.Exit(code=1)

    if filter_value and not resolved_decrypt:
        print_warning(
            "Filtering by value on SecureString parameters requires --decrypt. "
            "Encrypted values will not match."
        )

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

    # Apply filters
    filtered = result
    if filter_path:
        filtered = filtered.filter_by_path(filter_path)
    if filter_value:
        filtered = filtered.filter_by_value(filter_value)

    filter_parts: list[str] = []
    if filter_path:
        filter_parts.append(f"path ∋ '{filter_path}'")
    if filter_value:
        filter_parts.append(f"value ∋ '{filter_value}'")
    filter_summary = " AND ".join(filter_parts) if filter_parts else "(no filter applied)"

    if output == "json":
        render_json(filtered.to_json_list())
        return

    render_header(path=result.path, profile=resolved_profile, region=resolved_region)
    console.print(f"  [dim]Filter:[/dim] [bright_magenta]{filter_summary}[/bright_magenta]")
    console.print(
        f"  [dim]Total:[/dim] [count.badge]{result.total_count}[/count.badge]  "
        f"[dim]Matched:[/dim] [count.badge]{filtered.total_count}[/count.badge]"
    )
    console.print()

    if not filtered.parameters:
        print_info(f"No parameters matched: {filter_summary}")
        return

    render_parameter_table(
        filtered,
        decrypt=resolved_decrypt,
        conceal=resolved_conceal,
        show_arn=resolved_arn,
        show_env_variable=defaults.display.show_env_variable,
        show_value=defaults.display.show_value,
        show_type=resolved_show_type,
        show_full_path=defaults.display.show_full_path,
        show_version=resolved_show_version,
        show_last_modified=resolved_show_last_modified,
        max_value_length=defaults.display.max_value_length,
    )

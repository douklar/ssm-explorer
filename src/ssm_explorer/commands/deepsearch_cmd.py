"""
`deepsearch` command — deep search from SSM root across multiple accounts/regions.

READ-ONLY: uses SSM read APIs only. No AWS writes occur.
"""

from __future__ import annotations

from itertools import product
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
    render_multi_source_parameter_table,
)
from ssm_explorer.models.parameter import SSMParameter

ROOT_PATH = "/"
MAX_PROFILES = 3
MAX_REGIONS = 3

app = typer.Typer()


def _parse_csv_list(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",")]
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


@app.command("deepsearch")
def deepsearch_command(
    example_arg: Annotated[
        str | None,
        typer.Argument(
            help="Use 'example' to print deepsearch examples.",
            metavar="EXAMPLE",
        ),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            "-p",
            help="Comma-separated AWS profiles (max 3), e.g. dev,prod,stage.",
            metavar="PROFILES",
        ),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option(
            "--region",
            "-r",
            help="Comma-separated AWS regions (max 3), e.g. eu-west-1,eu-central-1.",
            metavar="REGIONS",
        ),
    ] = None,
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
        typer.Option("--filter-value", "-v", help="Match parameter value (case-insensitive).", metavar="PATTERN"),
    ] = None,
    decrypt: Annotated[
        bool | None,
        typer.Option("--decrypt/--no-decrypt", "-d/-D", help="Decrypt SecureString values."),
    ] = None,
    recursive: Annotated[
        bool | None,
        typer.Option("--recursive/--no-recursive", help="Recurse sub-paths."),
    ] = None,
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
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-C", help="Path to a custom config file.", metavar="FILE"),
    ] = None,
) -> None:
    """Deep search root path across profile/region combinations."""
    if is_example_arg(example_arg):
        print_command_examples("deepsearch")
        return

    active = load_config(config_file) if config_file else cfg

    profiles = _parse_csv_list(profile or "")
    regions = _parse_csv_list(region or "")

    if not profiles:
        print_error("At least one profile is required via --profile.")
        raise typer.Exit(code=1)
    if not regions:
        print_error("At least one region is required via --region.")
        raise typer.Exit(code=1)
    if len(profiles) > MAX_PROFILES:
        print_error(f"Maximum {MAX_PROFILES} profiles allowed. Got: {len(profiles)}.")
        raise typer.Exit(code=1)
    if len(regions) > MAX_REGIONS:
        print_error(f"Maximum {MAX_REGIONS} regions allowed. Got: {len(regions)}.")
        raise typer.Exit(code=1)

    defaults = active.defaults_for_profiles(*profiles)
    resolved_decrypt = decrypt if decrypt is not None else defaults.search.decrypt
    resolved_recurse = recursive if recursive is not None else defaults.search.recursive
    resolved_conceal = conceal if conceal is not None else defaults.display.conceal
    resolved_arn = show_arn if show_arn is not None else defaults.display.show_arn
    resolved_show_type = bool(show_type)
    resolved_show_version = bool(show_version)
    resolved_show_last_modified = bool(show_last_modified)

    if filter_value and not resolved_decrypt:
        print_warning(
            "Filtering by value on SecureString parameters requires --decrypt. "
            "Encrypted values will not match."
        )

    sources = list(product(profiles, regions))
    source_labels = [f"{prof}@{reg}" for prof, reg in sources]
    matched_sources: set[str] = set()
    failed_sources: list[str] = []
    rows: list[tuple[str, str, SSMParameter]] = []
    total_count = 0

    for prof, reg in sources:
        try:
            client = SSMClient(
                profile=prof,
                region=reg,
                fetch_workers=defaults.search.fetch_workers,
                max_get_tps=defaults.search.max_get_tps,
                max_describe_tps=defaults.search.max_describe_tps,
            )
            with error_console.status(
                f"[info]Fetching SSM parameters from {ROOT_PATH} ({prof}, {reg})...[/info]",
                spinner="dots",
            ):
                result = client.get_parameters_by_path(
                    ROOT_PATH,
                    recursive=resolved_recurse,
                    decrypt=resolved_decrypt,
                    strategy=defaults.search.fetch_strategy,
                )
        except (SSMAuthError, SSMAccessDeniedError, SSMClientError):
            failed_sources.append(f"{prof}@{reg}")
            continue

        total_count += result.total_count
        filtered = result
        if filter_path:
            filtered = filtered.filter_by_path(filter_path)
        if filter_value:
            filtered = filtered.filter_by_value(filter_value)

        if filtered.parameters:
            matched_sources.add(f"{prof}@{reg}")
        rows.extend((prof, reg, param) for param in filtered.parameters)

    if output == "json":
        payload = [
            {
                "profile": prof,
                "region": reg,
                **param.to_dict(conceal=resolved_conceal),
            }
            for prof, reg, param in rows
        ]
        render_json(payload)
        if failed_sources and not rows:
            raise typer.Exit(code=1)
        return

    console.print()
    console.print(f"  [dim]Sources searched:[/dim] [bright_cyan]{', '.join(source_labels)}[/bright_cyan]")
    matched_text = ", ".join(sorted(matched_sources)) if matched_sources else "(none)"
    console.print(f"  [dim]Matched sources:[/dim] [bright_magenta]{matched_text}[/bright_magenta]")
    console.print(
        f"  [dim]Total:[/dim] [count.badge]{total_count}[/count.badge]  "
        f"[dim]Matched:[/dim] [count.badge]{len(rows)}[/count.badge]"
    )
    if failed_sources:
        console.print(f"  [warning]Failed sources:[/warning] {', '.join(failed_sources)}")
    console.print()

    if not rows:
        print_info("No parameters matched for deepsearch filters.")
        if failed_sources:
            raise typer.Exit(code=1)
        return

    render_multi_source_parameter_table(
        rows,
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

    if failed_sources and not rows:
        raise typer.Exit(code=1)

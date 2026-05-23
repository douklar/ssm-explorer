"""
`list` command — list all parameters under a given SSM path.

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
    error_console,
    print_error,
    print_info,
    render_header,
    render_json,
    render_parameter_table,
)

app = typer.Typer()


@app.command("list")
def list_command(
    path: Annotated[
        str | None,
        typer.Argument(
            help=(
                "SSM Parameter Store path prefix (e.g. /my/path/to/var). "
                "Falls back to search.default_path in config if omitted."
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
    # ── Output ──────────────────────────────────────────────────────────
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
    List all parameters under the given SSM path.

    Displays each parameter as  ENV_VARIABLE → value  in a formatted table.
    All values are read from AWS SSM — no writes are ever performed.

    \b
    Examples:
      ssm-explorer list /my/path/to/var --profile my_profile_aws
      ssm-explorer list /my/path/to/var --profile my_profile_aws --decrypt
      ssm-explorer list /my/path/to/var --profile my_profile_aws --output json
      ssm-explorer list --profile my_profile_aws   # uses search.default_path from config
    """
    if is_example_arg(path):
        print_command_examples("list")
        return

    active = load_config(config_file) if config_file else cfg

    # Resolve with CLI flags overriding config
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

    if output == "json":
        render_json(result.to_json_list())
        return

    render_header(path=result.path, profile=resolved_profile, region=resolved_region)

    if not result.parameters:
        print_info(f"No parameters found under path: {resolved_path}")
        return

    render_parameter_table(
        result,
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

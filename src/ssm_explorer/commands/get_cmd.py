"""
`get` command — fetch and display a single SSM parameter by its full path/name.

READ-ONLY: only ssm:GetParameter is called. No AWS writes occur.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ssm_explorer.aws.ssm_client import (
    SSMAccessDeniedError,
    SSMAuthError,
    SSMClient,
    SSMClientError,
    SSMParameterNotFoundError,
)
from ssm_explorer.commands.examples import is_example_arg, print_command_examples
from ssm_explorer.config import cfg, load_config
from ssm_explorer.display import print_error, render_json, render_single_parameter

app = typer.Typer()


@app.command("get")
def get_command(
    name: Annotated[
        str,
        typer.Argument(
            help="Full SSM parameter name/path (e.g. /my/path/to/var/DATABASE_URL).",
            metavar="NAME",
        ),
    ],
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
    # ── Display options ─────────────────────────────────────────────────
    conceal: Annotated[
        bool | None,
        typer.Option(
            "--conceal/--no-conceal",
            help="Conceal SecureString values (first 4 chars + **** + char count).",
        ),
    ] = None,
    # ── Output ──────────────────────────────────────────────────────────
    output: Annotated[
        str,
        typer.Option(
            "--output", "-o",
            help="Output format: 'detail' (rich panel), 'value' (raw only), 'json'.",
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
    Get a single SSM parameter by its full name and display its details.

    All values are read from AWS SSM — no writes are ever performed.

    \b
    Examples:
      ssm-explorer get /my/path/to/var/DATABASE_URL --profile my_profile_aws
      ssm-explorer get /my/path/DATABASE_URL --profile my_profile_aws --decrypt
      ssm-explorer get /my/path/HOST --output value   # raw value (for shell scripting)
    """
    if is_example_arg(name):
        print_command_examples("get")
        return

    active = load_config(config_file) if config_file else cfg

    try:
        resolved_profile, resolved_region = active.resolve_aws(profile, region)
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    defaults = active.defaults_for_profiles(resolved_profile)
    resolved_decrypt = decrypt  if decrypt is not None else defaults.search.decrypt
    resolved_conceal = conceal  if conceal is not None else defaults.display.conceal

    try:
        client = SSMClient(
            profile=resolved_profile,
            region=resolved_region,
            max_get_tps=defaults.search.max_get_tps,
        )
        param = client.get_parameter(name, decrypt=resolved_decrypt)
    except SSMParameterNotFoundError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    except (SSMAuthError, SSMAccessDeniedError, SSMClientError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    if output == "json":
        render_json(param.to_dict(conceal=resolved_conceal))
        return

    if output == "value":
        # Raw value — useful for shell: export VAR=$(ssm-explorer get /path/VAR --output value)
        print(param.display_value(decrypt=resolved_decrypt, conceal=resolved_conceal))
        return

    render_single_parameter(param, decrypt=resolved_decrypt, conceal=resolved_conceal)

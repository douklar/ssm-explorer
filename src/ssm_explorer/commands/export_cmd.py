"""
`export` command — export SSM parameters to a .env or JSON file.

READ-ONLY (AWS): uses SSM read APIs only.

File saving is controlled by the  [output]  section of the config file.
It is DISABLED by default  (output.save = false).  The user must explicitly
enable it in their config file before any file will be written.

  [output]
  save = true
  path = "/home/user/my-exports/params.env"   # optional default path
"""

from __future__ import annotations

import json
from pathlib import Path
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
    print_success,
    print_warning,
)

app = typer.Typer()


@app.command("export")
def export_command(
    path: Annotated[
        str | None,
        typer.Argument(
            help=(
                "SSM path prefix to export. Falls back to search.default_path in config if omitted."
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
    # ── Export format ───────────────────────────────────────────────────
    fmt: Annotated[
        str | None,
        typer.Option("--format", help="Export format: 'env' or 'json'.", metavar="FORMAT"),
    ] = None,
    # ── Output destination ──────────────────────────────────────────────
    output_file: Annotated[
        Path | None,
        typer.Option(
            "--output-file",
            "-O",
            help=(
                "Destination file path. Requires output.save = true in config. "
                "If not given, prints to stdout (always allowed)."
            ),
            metavar="FILE",
        ),
    ] = None,
    overwrite: Annotated[
        bool | None,
        typer.Option("--overwrite/--no-overwrite", help="Overwrite existing output file."),
    ] = None,
    # ── Config override ─────────────────────────────────────────────────
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-C", help="Path to a custom config file.", metavar="FILE"),
    ] = None,
) -> None:
    """
    Export SSM parameters to a .env or JSON file (or stdout).

    File saving is opt-in — enable it in your config:

    \b
        [output]
        save = true
        path = "/path/to/output.env"   # optional default

    Printing to stdout is always allowed regardless of the save setting.

    \b
    Examples:
      ssm-explorer export /my/path --profile my_profile_aws              # stdout
      ssm-explorer export /my/path --profile my_profile_aws --decrypt --output-file .env
      ssm-explorer export /my/path --format json --output-file params.json
    """
    if is_example_arg(path):
        print_command_examples("export")
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
    resolved_fmt = fmt or defaults.output.format
    resolved_overwrite = overwrite if overwrite is not None else defaults.output.overwrite

    if not resolved_path:
        print_error(
            "No path provided. Pass PATH as an argument or set "
            "search.default_path or aws.profiles.<profile>.default_path in your config file."
        )
        raise typer.Exit(code=1)

    if resolved_fmt not in ("env", "json"):
        print_error(f"Unknown format '{resolved_fmt}'. Use 'env' or 'json'.")
        raise typer.Exit(code=1)

    # ── Read-only gate for file output ───────────────────────────────────
    # Resolve final output file path (CLI flag > config default)
    resolved_output_file: Path | None = output_file
    if resolved_output_file is None and defaults.output.path:
        resolved_output_file = Path(defaults.output.path)

    if resolved_output_file is not None:
        # Writing a file is only allowed when output.save = true
        try:
            defaults.assert_save_permitted()
        except RuntimeError as exc:
            print_error(str(exc))
            raise typer.Exit(code=1) from exc

    if not resolved_decrypt:
        print_warning(
            "SecureString values will NOT be decrypted. "
            "Use --decrypt to include plaintext in the export."
        )

    # ── Fetch from AWS (read-only) ───────────────────────────────────────
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

    # ── Build content ────────────────────────────────────────────────────
    if resolved_fmt == "env":
        content = result.to_env_file_content()
    else:
        content = json.dumps(result.to_json_list(), indent=2, default=str)

    # ── Write or print ───────────────────────────────────────────────────
    if resolved_output_file is None:
        # stdout — always permitted
        print(content)
        return

    out_path = Path(resolved_output_file)
    if out_path.exists() and not resolved_overwrite:
        print_error(
            f"File '{out_path}' already exists. Use --overwrite or set "
            "output.overwrite = true in your config."
        )
        raise typer.Exit(code=1)

    out_path.write_text(content, encoding="utf-8")
    try:
        out_path.chmod(0o600)
    except OSError:
        pass  # Fallback if OS doesn't support chmod (e.g. windows/some mounts)
    print_success(
        f"Exported {result.total_count} parameter(s) → '{out_path}' "
        f"(format: {resolved_fmt}, region: {resolved_region})"
    )

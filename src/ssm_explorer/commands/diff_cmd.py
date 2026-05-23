"""
`diff` command — compare SSM parameters across two paths, accounts, or regions.

READ-ONLY: uses SSM read APIs only for both environments.
No AWS writes occur.
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
    print_success,
    render_diff_table,
)
from ssm_explorer.models.parameter import DiffStatus, ParameterDiff

app = typer.Typer()


@app.command("diff")
def diff_command(
    path_a: Annotated[
        str | None,
        typer.Argument(
            help="Primary SSM path prefix (Source A).",
            metavar="PATH_A",
        ),
    ] = None,
    path_b: Annotated[
        str | None,
        typer.Argument(
            help="Secondary SSM path prefix (Source B). Defaults to PATH_A if omitted.",
            metavar="PATH_B",
        ),
    ] = None,
    # ── Connections ──────────────────────────────────────────────────────
    profile_a: Annotated[
        str | None,
        typer.Option("--profile-a", help="AWS profile for Source A.", metavar="PROFILE"),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option("--region", "-r", help="AWS region for both sources unless --region-a/--region-b is set.", metavar="REGION"),
    ] = None,
    region_a: Annotated[
        str | None,
        typer.Option("--region-a", help="AWS region for Source A.", metavar="REGION"),
    ] = None,
    profile_b: Annotated[
        str | None,
        typer.Option("--profile-b", help="AWS profile for Source B.", metavar="PROFILE"),
    ] = None,
    region_b: Annotated[
        str | None,
        typer.Option("--region-b", help="AWS region for Source B.", metavar="REGION"),
    ] = None,
    # ── Path overrides ──────────────────────────────────────────────────
    path_a_override: Annotated[
        str | None,
        typer.Option(
            "--path-a",
            help="Primary SSM path prefix (Source A). Overrides PATH_A argument.",
            metavar="PATH",
        ),
    ] = None,
    path_b_override: Annotated[
        str | None,
        typer.Option(
            "--path-b",
            help="Secondary SSM path prefix (Source B). Overrides PATH_B argument.",
            metavar="PATH",
        ),
    ] = None,
    # ── Fetch options ────────────────────────────────────────────────────
    decrypt: Annotated[
        bool | None,
        typer.Option("--decrypt/--no-decrypt", "-d/-D", help="Decrypt SecureString values to compare contents."),
    ] = None,
    recursive: Annotated[
        bool | None,
        typer.Option("--recursive/--no-recursive", help="Recurse sub-paths."),
    ] = None,
    # ── Display options ──────────────────────────────────────────────────
    conceal: Annotated[
        bool | None,
        typer.Option(
            "--conceal/--no-conceal",
            help="Conceal SecureString values in the terminal (first 4 chars + ****).",
        ),
    ] = None,
    filter_path: Annotated[
        str | None,
        typer.Option(
            "--filter-path",
            "--filter",
            "-f",
            help="Only diff parameters whose full path/name contains this pattern.",
            metavar="PATTERN",
        ),
    ] = None,
    exc_identicals: Annotated[
        bool,
        typer.Option(
            "--exc-identicals",
            help="Exclude parameters whose values and types are identical.",
        ),
    ] = False,
    exc_missing_a: Annotated[
        bool,
        typer.Option(
            "--exc-missing-a",
            help="Exclude parameters that exist only in Source B.",
        ),
    ] = False,
    # ── Config override ─────────────────────────────────────────────────
    config_file: Annotated[
        str | None,
        typer.Option("--config", "-C", help="Path to a custom config file.", metavar="FILE"),
    ] = None,
) -> None:
    """
    Compare parameters across two different environments (paths, accounts, or regions).

    Matches parameters between Source A and Source B based on their extracted ENV variable names.
    This allows comparing entirely different path roots (e.g. /dev/api vs /prod/api) gracefully.

    \b
    Examples:
      # Compare two paths in the same account
      ssm-explorer diff /app/dev /app/prod --profile my_profile_aws

      # Compare the same path across two different AWS accounts (profiles)
      ssm-explorer diff /app/config --profile-a dev_account --profile-b prod_account

      # Compare two different AWS accounts in the same region
      ssm-explorer diff /app/config --profile-a dev_account --profile-b prod_account --region eu-west-1

      # Compare across two regions in the same account
      ssm-explorer diff /app/config --profile-a default --region-a us-east-1 --region-b eu-west-1

      # Hide identical values and show differences only
      ssm-explorer diff /app/config --profile-a dev_account --profile-b prod_account --region eu-west-1 --exc-identicals

      # Hide parameters that exist only in Source B
      ssm-explorer diff /app/config --profile-a dev_account --profile-b prod_account --region eu-west-1 --exc-missing-a

      # Compare one path across regions, then only show matching parameter paths
      ssm-explorer diff --path-a /app/config --path-b /app/config --profile-a default --region-a us-east-1 --region-b eu-west-1 --filter-path browser
    """
    if is_example_arg(path_a):
        print_command_examples("diff")
        return

    active = load_config(config_file) if config_file else cfg

    try:
        res_prof_a, res_reg_a = active.resolve_aws(profile_a, region_a or region)

        # If profile_b/region_b are missing, fall back to profile_a/region_a.
        res_prof_b, res_reg_b = active.resolve_aws(
            profile_b or res_prof_a,
            region_b or region or (res_reg_a if not profile_b else None)
        )
    except ValueError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc
    defaults = active.defaults_for_profiles(res_prof_a, res_prof_b)

    # Resolve paths. Option flags exist for readability when the two sources
    # have many profile/region flags; positional paths remain supported.
    raw_path_a = path_a_override if path_a_override is not None else path_a
    raw_path_b = path_b_override if path_b_override is not None else path_b

    res_path_a = active.resolve_path(raw_path_a, res_prof_a)

    if raw_path_b:
        res_path_b = active.resolve_path(raw_path_b, res_prof_b)
    else:
        if raw_path_a:
            # User explicitly passed path_a, assume they want the same for path_b
            res_path_b = raw_path_a
        else:
            # Both paths omitted, resolve path_b based on its profile
            res_path_b = active.resolve_path(None, res_prof_b)

    if not res_path_a or not res_path_b:
        print_error("No path provided or found in config for one of the sources.")
        raise typer.Exit(code=1)

    res_decrypt   = decrypt   if decrypt   is not None else defaults.search.decrypt
    res_recurse   = recursive if recursive is not None else defaults.search.recursive
    res_conceal   = conceal   if conceal   is not None else defaults.display.conceal

    # Ensure at least SOMETHING is different between A and B
    if res_path_a == res_path_b and res_prof_a == res_prof_b and res_reg_a == res_reg_b:
        print_error("Source A and Source B are identical. There is nothing to diff!")
        raise typer.Exit(code=1)

    # 2. Fetch parameters from A and B
    try:
        client_a = SSMClient(
            profile=res_prof_a,
            region=res_reg_a,
            fetch_workers=defaults.search.fetch_workers,
            max_get_tps=defaults.search.max_get_tps,
            max_describe_tps=defaults.search.max_describe_tps,
        )
        with error_console.status(
            f"[info]Fetching Source A from {res_path_a} ({res_prof_a}, {res_reg_a})...[/info]",
            spinner="dots",
        ):
            result_a = client_a.get_parameters_by_path(
                res_path_a,
                recursive=res_recurse,
                decrypt=res_decrypt,
                strategy=defaults.search.fetch_strategy,
            )

        client_b = SSMClient(
            profile=res_prof_b,
            region=res_reg_b,
            fetch_workers=defaults.search.fetch_workers,
            max_get_tps=defaults.search.max_get_tps,
            max_describe_tps=defaults.search.max_describe_tps,
        )
        with error_console.status(
            f"[info]Fetching Source B from {res_path_b} ({res_prof_b}, {res_reg_b})...[/info]",
            spinner="dots",
        ):
            result_b = client_b.get_parameters_by_path(
                res_path_b,
                recursive=res_recurse,
                decrypt=res_decrypt,
                strategy=defaults.search.fetch_strategy,
            )
    except (SSMAuthError, SSMAccessDeniedError, SSMClientError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    if filter_path:
        result_a = result_a.filter_by_path(filter_path)
        result_b = result_b.filter_by_path(filter_path)

    # 3. Calculate Diff
    map_a = {p.env_variable_name: p for p in result_a.parameters}
    map_b = {p.env_variable_name: p for p in result_b.parameters}

    all_keys = sorted(set(map_a.keys()) | set(map_b.keys()))
    diffs: list[ParameterDiff] = []

    for key in all_keys:
        p_a = map_a.get(key)
        p_b = map_b.get(key)

        if p_a and not p_b:
            diffs.append(ParameterDiff(env_variable=key, status=DiffStatus.MISSING_IN_B, param_a=p_a, param_b=None))
        elif p_b and not p_a:
            diffs.append(ParameterDiff(env_variable=key, status=DiffStatus.MISSING_IN_A, param_a=None, param_b=p_b))
        elif p_a and p_b:
            # Check equality.
            # If not decrypted, we can't reliably diff SecureString values.
            # We assume they match unless types differ, but visually it will show as ***
            if p_a.type != p_b.type or p_a.value != p_b.value:
                diffs.append(ParameterDiff(env_variable=key, status=DiffStatus.CHANGED, param_a=p_a, param_b=p_b))
            else:
                diffs.append(ParameterDiff(env_variable=key, status=DiffStatus.IDENTICAL, param_a=p_a, param_b=p_b))

    rows = diffs
    if exc_identicals:
        rows = [d for d in rows if d.status != DiffStatus.IDENTICAL]
    if exc_missing_a:
        rows = [d for d in rows if d.status != DiffStatus.MISSING_IN_A]

    # Print a header describing the two sources
    from rich.columns import Columns
    from rich.panel import Panel
    from rich.text import Text

    src_a_text = Text.assemble(
        ("Source A\n", "bold #5b7fbf"),
        ("Path:    ", "dim white"), (res_path_a, "#d8dee9"), ("\n", ""),
        ("Profile: ", "dim white"), (res_prof_a, "bright_yellow"), ("\n", ""),
        ("Region:  ", "dim white"), (res_reg_a, "bright_green"),
    )
    src_b_text = Text.assemble(
        ("Source B\n", "bold bright_magenta"),
        ("Path:    ", "dim white"), (res_path_b, "#d8dee9"), ("\n", ""),
        ("Profile: ", "dim white"), (res_prof_b, "bright_yellow"), ("\n", ""),
        ("Region:  ", "dim white"), (res_reg_b, "bright_green"),
    )

    console.print()
    console.print(Columns([Panel(src_a_text, expand=True), Panel(src_b_text, expand=True)]))
    console.print()

    if not rows:
        if not diffs:
            print_info("Neither source contains any parameters.")
        elif all(d.status == DiffStatus.IDENTICAL for d in diffs):
            print_success(f"All {len(diffs)} parameters are IDENTICAL across both environments.")
        else:
            print_info("No diff rows to display after exclusions.")
        return

    # Render table
    render_diff_table(
        rows,
        decrypt=res_decrypt,
        conceal=res_conceal,
        max_value_length=defaults.display.max_value_length
    )

    # Summary
    missing_a = sum(1 for d in rows if d.status == DiffStatus.MISSING_IN_A)
    missing_b = sum(1 for d in rows if d.status == DiffStatus.MISSING_IN_B)
    changed = sum(1 for d in rows if d.status == DiffStatus.CHANGED)
    identical = sum(1 for d in rows if d.status == DiffStatus.IDENTICAL)

    summary = Text()
    summary.append("  [dim]Diff Summary:[/dim]  ")
    summary_parts = 0
    if identical:
        summary.append(f"{identical} Identical", style="dim green")
        summary_parts += 1
    if missing_a:
        if summary_parts:
            summary.append(" • ", style="dim")
        summary.append(f"{missing_a} Missing in A", style="bold red")
        summary_parts += 1
    if missing_b:
        if summary_parts:
            summary.append(" • ", style="dim")
        summary.append(f"{missing_b} Missing in B", style="bold green")
        summary_parts += 1
    if changed:
        if summary_parts:
            summary.append(" • ", style="dim")
        summary.append(f"{changed} Changed", style="bold yellow")

    console.print(summary)
    console.print()

"""
Rich-based terminal renderer for SSM Explorer.

All terminal output styling is centralised here to make it easy to
adjust the look-and-feel without touching business logic.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from ssm_explorer.models.parameter import (
    DiffStatus,
    ParameterDiff,
    ParameterType,
    SearchResult,
    SSMParameter,
)

# ---------------------------------------------------------------------------
# Custom theme — one place to change ALL colours
# ---------------------------------------------------------------------------
SSM_THEME = Theme(
    {
        "header.title": "bold #5b7fbf",
        "header.subtitle": "dim #5b7fbf",
        "table.header": "bold bright_white on #1e3a5f",
        "param.name": "bold bright_yellow",
        "param.value.plain": "bright_white",
        "param.value.secure": "dim italic yellow",
        "param.value.masked": "dim italic red",
        "param.type.string": "bright_green",
        "param.type.stringlist": "bright_blue",
        "param.type.secure": "bright_red",
        "param.path": "#d8dee9",
        "count.badge": "bold bright_magenta",
        "success": "bold bright_green",
        "warning": "bold bright_yellow",
        "error": "bold bright_red",
        "info": "#8fbcbb",
        "muted": "dim white",
    }
)

console = Console(theme=SSM_THEME)
error_console = Console(stderr=True, theme=SSM_THEME)


# ---------------------------------------------------------------------------
# Banner / header
# ---------------------------------------------------------------------------


def render_header(path: str, profile: str, region: str) -> None:
    """Print a stylised header panel for the query."""
    title = Text("🔍  SSM Parameter Store Explorer", style="header.title")
    subtitle = Text.assemble(
        ("Path: ", "dim white"),
        (path, "#d8dee9"),
        ("   •   ", "dim"),
        ("Profile: ", "dim white"),
        (profile, "bright_yellow"),
        ("   •   ", "dim"),
        ("Region: ", "dim white"),
        (region, "bright_green"),
    )
    panel = Panel(
        subtitle,
        title=title,
        border_style="#5b7fbf",
        padding=(0, 2),
        expand=True,
    )
    console.print()
    console.print(panel)
    console.print()


# ---------------------------------------------------------------------------
# Parameter tables
# ---------------------------------------------------------------------------


def render_parameter_table(
    result: SearchResult,
    *,
    decrypt: bool = False,
    conceal: bool = True,
    show_arn: bool = False,
    max_value_length: int = 80,
    show_env_variable: bool = True,
    show_value: bool = True,
    show_type: bool = True,
    show_full_path: bool = True,
    show_version: bool = True,
    show_last_modified: bool = True,
) -> None:
    """
    Render the full parameter table for a SearchResult.

    Args:
        result:           The search result to display.
        decrypt:          Whether SecureString values were decrypted.
        conceal:          Whether to conceal SecureString values (first 4 chars + ****).
        show_arn:         Whether to include the ARN column.
        max_value_length: Max characters to show in the Value column.
        show_env_variable: Whether to include ENV variable name column.
        show_value:       Whether to include Value column.
        show_type:        Whether to include Type column.
        show_full_path:   Whether to include the full SSM parameter path.
        show_version:     Whether to include the Version column.
        show_last_modified: Whether to include the Last Modified column.
    """
    if not result.parameters:
        console.print(
            Panel(
                "  No parameters found for this path.",
                border_style="yellow",
                title="[warning]⚠ No Results[/warning]",
            )
        )
        return

    count_text = Text.assemble(
        ("  Found ", "dim white"),
        (str(result.total_count), "count.badge"),
        (" parameter(s)", "dim white"),
    )
    if decrypt and conceal:
        count_text.append(
            "  🔒 SecureString values are concealed — use --no-conceal to reveal",
            style="dim yellow",
        )
    console.print(count_text)
    console.print()

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="table.header",
        border_style="dim #5b7fbf",
        expand=True,
        show_lines=False,
        padding=(0, 1),
    )

    # Define columns
    if show_env_variable:
        table.add_column("ENV Variable", style="param.name", min_width=20, no_wrap=True)
    if show_full_path:
        table.add_column("Full Path", style="param.path", min_width=24, overflow="fold")
    if show_value:
        table.add_column("Value", style="param.value.plain", max_width=max_value_length)
    if show_type:
        table.add_column("Type", justify="center", min_width=12)
    if show_version:
        table.add_column("Ver", justify="right", style="muted", min_width=4)
    if show_last_modified:
        table.add_column("Last Modified", justify="right", style="muted", min_width=12)
    if show_arn:
        table.add_column("ARN", style="muted", max_width=60)

    for param in result.parameters:
        row = _build_table_row(
            param,
            decrypt=decrypt,
            conceal=conceal,
            max_value_length=max_value_length,
            show_env_variable=show_env_variable,
            show_value=show_value,
            show_type=show_type,
            show_full_path=show_full_path,
            show_version=show_version,
            show_last_modified=show_last_modified,
        )
        if show_arn:
            row.append(param.arn or "-")
        table.add_row(*row)

    console.print(table)
    console.print()


def render_multi_source_parameter_table(
    rows: list[tuple[str, str, SSMParameter]],
    *,
    decrypt: bool = False,
    conceal: bool = True,
    show_arn: bool = False,
    max_value_length: int = 80,
    show_env_variable: bool = True,
    show_value: bool = True,
    show_type: bool = True,
    show_full_path: bool = True,
    show_version: bool = True,
    show_last_modified: bool = True,
) -> None:
    """Render merged rows from multiple profile+region sources."""
    if not rows:
        console.print(
            Panel(
                "  No parameters matched.",
                border_style="yellow",
                title="[warning]⚠ No Results[/warning]",
            )
        )
        return

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="table.header",
        border_style="dim #5b7fbf",
        expand=True,
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Profile", style="bright_yellow", min_width=12, no_wrap=True)
    table.add_column("Region", style="bright_green", min_width=12, no_wrap=True)
    if show_env_variable:
        table.add_column("ENV Variable", style="param.name", min_width=20, no_wrap=True)
    if show_full_path:
        table.add_column("Full Path", style="param.path", min_width=24, overflow="fold")
    if show_value:
        table.add_column("Value", style="param.value.plain", max_width=max_value_length)
    if show_type:
        table.add_column("Type", justify="center", min_width=12)
    if show_version:
        table.add_column("Ver", justify="right", style="muted", min_width=4)
    if show_last_modified:
        table.add_column("Last Modified", justify="right", style="muted", min_width=12)
    if show_arn:
        table.add_column("ARN", style="muted", max_width=60)

    for profile, region, param in rows:
        row = [profile, region]
        row.extend(
            _build_table_row(
                param,
                decrypt=decrypt,
                conceal=conceal,
                max_value_length=max_value_length,
                show_env_variable=show_env_variable,
                show_value=show_value,
                show_type=show_type,
                show_full_path=show_full_path,
                show_version=show_version,
                show_last_modified=show_last_modified,
            )
        )
        if show_arn:
            row.append(param.arn or "-")
        table.add_row(*row)

    console.print(table)
    console.print()


def _build_table_row(
    param: SSMParameter,
    *,
    decrypt: bool,
    conceal: bool = True,
    max_value_length: int,
    show_env_variable: bool = True,
    show_value: bool = True,
    show_type: bool = True,
    show_full_path: bool = True,
    show_version: bool = True,
    show_last_modified: bool = True,
) -> list[str | Text]:
    """Build a single table row for a parameter."""
    # ENV variable name
    env_name = Text(param.env_variable_name, style="param.name")

    # Value — use display_value which applies concealment logic
    display = param.display_value(decrypt=decrypt, conceal=conceal)
    if param.is_encrypted and not decrypt:
        # Never fetched — lock icon hint
        value_text = Text(display, style="param.value.masked")
    elif param.is_encrypted and decrypt and conceal:
        # Concealed (first 4 + ****) — amber warning colour
        value_text = Text(display, style="param.value.secure")
    else:
        raw_val = display
        if len(raw_val) > max_value_length:
            raw_val = raw_val[:max_value_length] + "…"
        value_text = Text(raw_val, style="param.value.plain")

    # Type badge
    type_styles = {
        ParameterType.STRING: ("String", "param.type.string"),
        ParameterType.STRING_LIST: ("StringList", "param.type.stringlist"),
        ParameterType.SECURE_STRING: ("SecureString 🔒", "param.type.secure"),
    }
    type_label, type_style = type_styles.get(param.type, (param.type.value, "param.type.string"))
    type_text = Text(type_label, style=type_style)

    # Version
    version = str(param.version)

    # Last modified
    last_mod = "-"
    if param.last_modified:
        last_mod = param.last_modified.strftime("%Y-%m-%d")

    row: list[str | Text] = []
    if show_env_variable:
        row.append(env_name)
    if show_full_path:
        row.append(param.name)
    if show_value:
        row.append(value_text)
    if show_type:
        row.append(type_text)
    if show_version:
        row.append(version)
    if show_last_modified:
        row.append(last_mod)
    return row


# ---------------------------------------------------------------------------
# Single parameter detail view
# ---------------------------------------------------------------------------


def render_single_parameter(
    param: SSMParameter, *, decrypt: bool = False, conceal: bool = True
) -> None:
    """Render a detailed view of a single parameter."""
    console.print()

    type_styles = {
        ParameterType.STRING: "param.type.string",
        ParameterType.STRING_LIST: "param.type.stringlist",
        ParameterType.SECURE_STRING: "param.type.secure",
    }
    type_style = type_styles.get(param.type, "param.type.string")

    display = param.display_value(decrypt=decrypt, conceal=conceal)
    if param.is_encrypted and not decrypt:
        value_display = Text(display, style="param.value.masked")
    elif param.is_encrypted and decrypt and conceal:
        value_display = Text(display, style="param.value.secure")
    else:
        value_display = Text(display, style="param.value.plain")

    # Show a hint line below the value when concealed
    conceal_hint = ""
    if param.is_encrypted and decrypt and conceal:
        conceal_hint = (
            "\n  [dim yellow]  ↳ concealed — use --no-conceal to reveal full value[/dim yellow]"
        )

    content = Text.assemble(
        ("\n  Full Name:     ", "dim white"),
        (param.name, "#d8dee9"),
        ("\n  ENV Variable:  ", "dim white"),
        (param.env_variable_name, "param.name"),
        ("\n  Value:         ", "dim white"),
    )
    content.append_text(value_display)
    if conceal_hint:
        console.print()  # will print hint separately after panel
    content.append_text(
        Text.assemble(
            ("\n  Type:          ", "dim white"),
            (param.type.value, type_style),
            ("\n  Version:       ", "dim white"),
            (str(param.version), "bright_white"),
            ("\n  Last Modified: ", "dim white"),
            (
                param.last_modified.strftime("%Y-%m-%d %H:%M:%S UTC")
                if param.last_modified
                else "-",
                "muted",
            ),
            ("\n  ARN:           ", "dim white"),
            (param.arn or "-", "muted"),
            ("\n  Data Type:     ", "dim white"),
            (param.data_type, "muted"),
            ("\n", ""),
        )
    )

    panel = Panel(
        content,
        title=Text("📦  Parameter Details", style="header.title"),
        border_style="#5b7fbf",
        padding=(0, 1),
    )
    console.print(panel)
    if conceal_hint:
        console.print(conceal_hint)
    console.print()


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


JsonObject = Mapping[str, object]


def render_json(data: Sequence[JsonObject] | JsonObject) -> None:
    """Print data as pretty-printed JSON (no Rich styling for pipe-friendliness)."""
    print(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# Diff rendering
# ---------------------------------------------------------------------------


def render_diff_table(
    diffs: list[ParameterDiff],
    *,
    decrypt: bool,
    conceal: bool,
    max_value_length: int,
) -> None:
    """Render a Rich table showing parameter differences."""
    table = Table(
        title=Text("SSM Parameter Diff", style="header.title"),
        border_style="dim blue",
        header_style="bold #5b7fbf",
        show_lines=True,
    )
    table.add_column("ENV Variable", style="white", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Source A", overflow="fold")
    table.add_column("Source B", overflow="fold")

    for diff in diffs:
        # Determine status styling
        if diff.status == DiffStatus.MISSING_IN_A:
            status = Text("+ Added to B", style="bold green")
        elif diff.status == DiffStatus.MISSING_IN_B:
            status = Text("- Missing in B", style="bold red")
        elif diff.status == DiffStatus.CHANGED:
            status = Text("~ Changed", style="bold yellow")
        else:
            status = Text("= Identical", style="dim green")

        # Format values
        def format_val(p: SSMParameter | None) -> Text:
            if not p:
                return Text("-", style="dim")
            display = p.display_value(decrypt=decrypt, conceal=conceal, max_length=max_value_length)
            # Add type hint if it's not a standard String
            type_hint = ""
            if p.type != ParameterType.STRING:
                type_hint = f" [{p.type.value}]"

            txt = Text(display, style="dim white" if "SecureString" in p.type.value else "white")
            if type_hint:
                txt.append(type_hint, style="dim magenta")
            return txt

        table.add_row(
            diff.env_variable,
            status,
            format_val(diff.param_a),
            format_val(diff.param_b),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Status / feedback messages
# ---------------------------------------------------------------------------


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[success]✔  {message}[/success]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[warning]⚠  {message}[/warning]")


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    error_console.print(f"[error]✖  {message}[/error]")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[info]ℹ  {message}[/info]")

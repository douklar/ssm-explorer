"""
SSM Explorer — CLI entry point.

READ-ONLY TOOL
All AWS operations are strictly read-only:
  • ssm:GetParameter
  • ssm:GetParameters
  • ssm:GetParametersByPath
  • ssm:DescribeParameters
No write, put, delete or modify calls are ever made to AWS.
"""

from __future__ import annotations

from typing import Annotated

import typer
import typer.rich_utils as typer_rich_utils

from ssm_explorer import __version__
from ssm_explorer.commands.browse_cmd import browse_command
from ssm_explorer.commands.check_cmd import check_command
from ssm_explorer.commands.config_cmd import app as config_app
from ssm_explorer.commands.deepsearch_cmd import deepsearch_command
from ssm_explorer.commands.diff_cmd import diff_command
from ssm_explorer.commands.export_cmd import export_command
from ssm_explorer.commands.get_cmd import get_command
from ssm_explorer.commands.install_cmd import install_command, uninstall_command
from ssm_explorer.commands.list_cmd import list_command
from ssm_explorer.commands.search_cmd import search_command
from ssm_explorer.display import console

HELP_ACCENT = "#5b7fbf"

typer_rich_utils.STYLE_COMMANDS_PANEL_BORDER = HELP_ACCENT
typer_rich_utils.STYLE_COMMANDS_TABLE_BORDER_STYLE = f"dim {HELP_ACCENT}"
typer_rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = f"bold {HELP_ACCENT}"
typer_rich_utils.STYLE_OPTIONS_PANEL_BORDER = HELP_ACCENT
typer_rich_utils.STYLE_OPTIONS_TABLE_BORDER_STYLE = f"dim {HELP_ACCENT}"
typer_rich_utils.STYLE_OPTION = f"bold {HELP_ACCENT}"
typer_rich_utils.STYLE_SWITCH = f"bold {HELP_ACCENT}"
typer_rich_utils.STYLE_USAGE_COMMAND = f"bold {HELP_ACCENT}"

# ---------------------------------------------------------------------------
# Root application
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="ssm-explorer",
    help=(
        "🔍 [bold #5b7fbf]SSM Explorer[/bold #5b7fbf] — "
        "AWS Systems Manager Parameter Store CLI.\n\n"
        "Browse, search, filter and inspect SSM parameters with beautiful "
        "terminal output.\n\n"
        "[bold]🔒 Read-only:[/bold] SSM read APIs only; no AWS write calls.\n\n"
        "Run [bold]ssm-explorer config init[/bold] to create your config file.\n"
        "Run [bold]ssm-explorer COMMAND example[/bold] to see common examples.\n"
        "Run [bold]ssm-explorer COMMAND --help[/bold] for command-specific options."
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# ── Leaf commands ────────────────────────────────────────────────────────────
app.command("list", help="List parameters. Use: ssm-explorer list example")(list_command)
app.command("search", help="Filter parameters. Use: ssm-explorer search example")(search_command)
app.command(
    "deepsearch",
    help="Deep search across accounts/regions from root path. Use: ssm-explorer deepsearch example",
)(deepsearch_command)
app.command("get", help="Get one parameter. Use: ssm-explorer get example")(get_command)
app.command("export", help="Export parameters. Use: ssm-explorer export example")(export_command)
app.command("browse", help="Interactive browser. Use: ssm-explorer browse example")(browse_command)
app.command("diff", help="Compare parameters. Use: ssm-explorer diff example")(diff_command)
app.command("check", help="Validate install, config, AWS profile, region, and CLI commands.")(
    check_command
)
app.command(
    "install", help="Install local Poetry wrapper so ssm-explorer runs from any directory."
)(install_command)
app.command("uninstall", help="Remove local Poetry wrapper installed by ssm-explorer install.")(
    uninstall_command
)

# ── Sub-app: config ──────────────────────────────────────────────────────────
app.add_typer(
    config_app,
    name="config",
    help="View, initialise, and inspect the configuration file.",
)


# ---------------------------------------------------------------------------
# Global --version flag
# ---------------------------------------------------------------------------


def _version_callback(value: bool) -> None:
    if value:
        console.print(
            f"[bold #5b7fbf]ssm-explorer[/bold #5b7fbf] [bright_white]v{__version__}[/bright_white]"
        )
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            help="Show the application version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """SSM Explorer root — handles global flags."""


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()

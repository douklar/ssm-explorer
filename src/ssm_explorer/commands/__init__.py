"""Commands package."""

from ssm_explorer.commands.browse_cmd import app as browse_app
from ssm_explorer.commands.config_cmd import app as config_app
from ssm_explorer.commands.deepsearch_cmd import app as deepsearch_app
from ssm_explorer.commands.diff_cmd import diff_command
from ssm_explorer.commands.export_cmd import app as export_app
from ssm_explorer.commands.get_cmd import app as get_app
from ssm_explorer.commands.list_cmd import app as list_app
from ssm_explorer.commands.search_cmd import app as search_app

__all__ = ["list_app", "search_app", "deepsearch_app", "get_app", "diff_command", "export_app", "browse_app", "config_app"]

"""Reusable command example output."""

from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.syntax import Syntax

from ssm_explorer.display import console

EXAMPLES: dict[str, str] = {
    "list": """\
ssm-explorer list /my/app/prod --profile my_profile --region eu-west-1
ssm-explorer list /my/app/prod --profile my_profile --decrypt
ssm-explorer list --profile my_profile
ssm-explorer list /my/app/prod --profile my_profile --output json
""",
    "search": """\
ssm-explorer search /my/app/prod --profile my_profile --filter-path DATABASE
ssm-explorer search /my/app/prod --profile my_profile --filter-value postgres --decrypt
ssm-explorer search /my/app/prod --profile my_profile --filter-path DB --filter-value 5432
ssm-explorer search --profile my_profile --filter-path API
""",
    "deepsearch": """\
ssm-explorer deepsearch --profile dev,prod --region eu-west-1 --filter-path DATABASE
ssm-explorer deepsearch --profile dev,prod --region eu-west-1,eu-central-1 --filter-value postgres --decrypt
ssm-explorer deepsearch --profile dev --region eu-west-1 --filter-path API --output json
ssm-explorer deepsearch example
""",
    "get": """\
ssm-explorer get /my/app/prod/DATABASE_URL --profile my_profile --region eu-west-1
ssm-explorer get /my/app/prod/API_KEY --profile my_profile --decrypt
ssm-explorer get /my/app/prod/HOST --profile my_profile --output value
ssm-explorer get /my/app/prod/HOST --profile my_profile --output json
""",
    "export": """\
ssm-explorer export /my/app/prod --profile my_profile
ssm-explorer export /my/app/prod --profile my_profile --format json
ssm-explorer export /my/app/prod --profile my_profile --decrypt --output-file params.env
ssm-explorer export /my/app/prod --profile my_profile --format json --output-file params.json --overwrite
""",
    "browse": """\
ssm-explorer browse /my/app/prod --profile my_profile
ssm-explorer browse /my/app/prod --profile my_profile --decrypt
ssm-explorer browse --profile my_profile
ssm-explorer browse /my/app/prod --profile my_profile --output value
""",
    "diff": """\
ssm-explorer diff /app/dev /app/prod --profile my_profile
ssm-explorer diff /app/config --profile-a dev_account --profile-b prod_account
ssm-explorer diff /app/config --profile-a dev_account --profile-b prod_account --region eu-west-1
ssm-explorer diff /app/config --profile-a default --region-a us-east-1 --region-b eu-west-1
ssm-explorer diff /app/config --profile-a dev_account --profile-b prod_account --region eu-west-1 --exc-identicals
ssm-explorer diff /app/config --profile-a dev_account --profile-b prod_account --region eu-west-1 --exc-missing-a
ssm-explorer diff --path-a /app/dev --path-b /app/prod --profile-a dev_account --profile-b prod_account --filter-path DATABASE
""",
}


def is_example_arg(value: str | None) -> bool:
    return (value or "").strip().lower() in {"example", "examples", "exmaple"}


def print_command_examples(command: str) -> None:
    examples = EXAMPLES[command].strip()
    syntax = Syntax(examples, "bash", theme="monokai", word_wrap=True)
    console.print(
        Panel(
            syntax,
            title=f"[bold #5b7fbf]ssm-explorer {command} examples[/bold #5b7fbf]",
            border_style="#5b7fbf",
            box=box.ROUNDED,
        )
    )

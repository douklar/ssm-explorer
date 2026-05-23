"""Tests for table column visibility in renderer."""
# mypy: disable-error-code="no-untyped-def,unused-ignore"

from __future__ import annotations

from rich.table import Table

from ssm_explorer.display.renderer import render_parameter_table


def _last_printed_table(captured: list[object]) -> Table:
    for item in reversed(captured):
        if isinstance(item, Table):
            return item
    raise AssertionError("No table rendered")


def test_render_parameter_table_allows_three_column_layout(
    sample_search_result,
    monkeypatch,
):
    captured: list[object] = []

    def fake_print(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured.extend(args)

    monkeypatch.setattr("ssm_explorer.display.renderer.console.print", fake_print)

    render_parameter_table(
        sample_search_result,
        decrypt=False,
        conceal=True,
        show_arn=False,
        show_env_variable=True,
        show_value=True,
        show_type=False,
        show_full_path=True,
        show_version=False,
        show_last_modified=False,
        max_value_length=80,
    )

    table = _last_printed_table(captured)
    headers = [str(column.header) for column in table.columns]
    assert headers == ["ENV Variable", "Full Path", "Value"]


def test_render_parameter_table_shows_all_optional_columns(
    sample_search_result,
    monkeypatch,
):
    captured: list[object] = []

    def fake_print(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured.extend(args)

    monkeypatch.setattr("ssm_explorer.display.renderer.console.print", fake_print)

    render_parameter_table(
        sample_search_result,
        decrypt=False,
        conceal=True,
        show_arn=True,
        show_env_variable=True,
        show_value=True,
        show_type=True,
        show_full_path=True,
        show_version=True,
        show_last_modified=True,
        max_value_length=80,
    )

    table = _last_printed_table(captured)
    headers = [str(column.header) for column in table.columns]
    assert headers == [
        "ENV Variable",
        "Full Path",
        "Value",
        "Type",
        "Ver",
        "Last Modified",
        "ARN",
    ]

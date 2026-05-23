"""Tests for default table columns in list/search commands."""
# mypy: disable-error-code="no-untyped-def,unused-ignore"

from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from ssm_explorer.config import AppConfig
from ssm_explorer.main import app
from ssm_explorer.models.parameter import ParameterType, SearchResult, SSMParameter

runner = CliRunner()


class FakeSSMClient:
    def __init__(self, profile: str, region: str, **_: Any) -> None:
        self.profile = profile
        self.region = region

    def get_parameters_by_path(
        self,
        path: str,
        *,
        recursive: bool,
        decrypt: bool,
        strategy: str = "path",
    ) -> SearchResult:
        return SearchResult(
            path=path,
            parameters=[
                SSMParameter(
                    name="/test/browser/API_URL",
                    value="https://example.test",
                    type=ParameterType.STRING,
                )
            ],
            profile=self.profile,
            region=self.region,
        )


def _stale_config_with_extra_columns() -> AppConfig:
    return AppConfig.model_validate(
        {
            "aws": {"profile": "test-profile", "region": "eu-west-1"},
            "search": {"decrypt": True, "recursive": True},
            "display": {
                "show_env_variable": True,
                "show_full_path": True,
                "show_value": True,
                "show_type": True,
                "show_version": True,
                "show_last_modified": True,
            },
        }
    )


def test_search_defaults_to_three_table_columns_even_with_stale_config(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_render_parameter_table(result, **kwargs):
        captured["kwargs"] = kwargs

    monkeypatch.setattr("ssm_explorer.commands.search_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr(
        "ssm_explorer.commands.search_cmd.render_parameter_table", fake_render_parameter_table
    )
    monkeypatch.setattr("ssm_explorer.commands.search_cmd.cfg", _stale_config_with_extra_columns())

    result = runner.invoke(
        app,
        [
            "search",
            "/test",
            "--filter-path",
            "browser",
            "--profile",
            "test-profile",
            "--region",
            "eu-west-1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["kwargs"]["show_type"] is False
    assert captured["kwargs"]["show_version"] is False
    assert captured["kwargs"]["show_last_modified"] is False


def test_search_extra_columns_require_explicit_flags(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_render_parameter_table(result, **kwargs):
        captured["kwargs"] = kwargs

    monkeypatch.setattr("ssm_explorer.commands.search_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr(
        "ssm_explorer.commands.search_cmd.render_parameter_table", fake_render_parameter_table
    )
    monkeypatch.setattr("ssm_explorer.commands.search_cmd.cfg", _stale_config_with_extra_columns())

    result = runner.invoke(
        app,
        [
            "search",
            "/test",
            "--filter-path",
            "browser",
            "--profile",
            "test-profile",
            "--region",
            "eu-west-1",
            "--show-type",
            "--show-version",
            "--show-last-modified",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["kwargs"]["show_type"] is True
    assert captured["kwargs"]["show_version"] is True
    assert captured["kwargs"]["show_last_modified"] is True


def test_list_defaults_to_three_table_columns_even_with_stale_config(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_render_parameter_table(result, **kwargs):
        captured["kwargs"] = kwargs

    monkeypatch.setattr("ssm_explorer.commands.list_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr(
        "ssm_explorer.commands.list_cmd.render_parameter_table", fake_render_parameter_table
    )
    monkeypatch.setattr("ssm_explorer.commands.list_cmd.cfg", _stale_config_with_extra_columns())

    result = runner.invoke(
        app,
        [
            "list",
            "/test",
            "--profile",
            "test-profile",
            "--region",
            "eu-west-1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["kwargs"]["show_type"] is False
    assert captured["kwargs"]["show_version"] is False
    assert captured["kwargs"]["show_last_modified"] is False

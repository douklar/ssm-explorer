"""Tests for deepsearch command output and source indicators."""
# mypy: disable-error-code="no-untyped-def,unused-ignore"

from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from ssm_explorer.config import AppConfig
from ssm_explorer.main import app
from ssm_explorer.models.parameter import ParameterType, SearchResult, SSMParameter

runner = CliRunner()


class FakeSSMClient:
    calls: list[dict[str, Any]] = []

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
        self.calls.append(
            {
                "profile": self.profile,
                "region": self.region,
                "path": path,
                "recursive": recursive,
                "decrypt": decrypt,
                "strategy": strategy,
            }
        )
        return SearchResult(
            path=path,
            parameters=[
                SSMParameter(
                    name=f"/{self.profile}/{self.region}/API_URL",
                    value=f"https://{self.profile}-{self.region}.example.test",
                    type=ParameterType.STRING,
                ),
            ],
            profile=self.profile,
            region=self.region,
        )


def test_deepsearch_prints_source_indicators_and_profile_region_columns(monkeypatch):
    FakeSSMClient.calls = []
    captured: dict[str, Any] = {}

    def fake_render_multi_source_parameter_table(rows, **kwargs):  # type: ignore[no-untyped-def]
        captured["rows"] = rows
        captured["kwargs"] = kwargs

    monkeypatch.setattr("ssm_explorer.commands.deepsearch_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr(
        "ssm_explorer.commands.deepsearch_cmd.render_multi_source_parameter_table",
        fake_render_multi_source_parameter_table,
    )
    monkeypatch.setattr(
        "ssm_explorer.commands.deepsearch_cmd.cfg",
        AppConfig.model_validate(
            {
                "aws": {"profile": "fallback", "region": "eu-west-1"},
                "search": {"decrypt": True, "recursive": True},
            }
        ),
    )

    result = runner.invoke(
        app,
        [
            "deepsearch",
            "--profile",
            "dev,prod",
            "--region",
            "eu-west-1",
            "--filter-path",
            "API_URL",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Sources searched:" in result.output
    assert "dev@eu-west-1, prod@eu-west-1" in result.output
    assert "Matched sources:" in result.output
    assert "dev@eu-west-1" in result.output
    assert "prod@eu-west-1" in result.output

    rows = captured["rows"]
    assert len(rows) == 2
    assert rows[0][0] == "dev"
    assert rows[0][1] == "eu-west-1"
    assert rows[1][0] == "prod"
    assert rows[1][1] == "eu-west-1"
    assert [call["path"] for call in FakeSSMClient.calls] == ["/", "/"]


def test_deepsearch_no_match_still_prints_source_indicators(monkeypatch):
    class NoMatchClient(FakeSSMClient):
        def get_parameters_by_path(self, path: str, *, recursive: bool, decrypt: bool, strategy: str = "path") -> SearchResult:
            self.calls.append(
                {
                    "profile": self.profile,
                    "region": self.region,
                    "path": path,
                }
            )
            return SearchResult(path=path, parameters=[], profile=self.profile, region=self.region)

    monkeypatch.setattr("ssm_explorer.commands.deepsearch_cmd.SSMClient", NoMatchClient)
    monkeypatch.setattr(
        "ssm_explorer.commands.deepsearch_cmd.cfg",
        AppConfig.model_validate(
            {
                "aws": {"profile": "fallback", "region": "eu-west-1"},
                "search": {"decrypt": True, "recursive": True},
            }
        ),
    )

    result = runner.invoke(
        app,
        [
            "deepsearch",
            "--profile",
            "dev",
            "--region",
            "eu-west-1,eu-central-1",
            "--filter-path",
            "DOES_NOT_EXIST",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Sources searched:" in result.output
    assert "dev@eu-west-1, dev@eu-central-1" in result.output
    assert "Matched sources:" in result.output
    assert "(none)" in result.output
    assert "No parameters matched" in result.output


def test_deepsearch_json_includes_profile_and_region(monkeypatch):
    monkeypatch.setattr("ssm_explorer.commands.deepsearch_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr(
        "ssm_explorer.commands.deepsearch_cmd.cfg",
        AppConfig.model_validate(
            {
                "aws": {"profile": "fallback", "region": "eu-west-1"},
                "search": {"decrypt": True, "recursive": True},
            }
        ),
    )

    result = runner.invoke(
        app,
        [
            "deepsearch",
            "--profile",
            "dev",
            "--region",
            "eu-west-1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert '"profile": "dev"' in result.output
    assert '"region": "eu-west-1"' in result.output

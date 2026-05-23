"""Tests for the diff command CLI options."""
# mypy: disable-error-code="no-untyped-def,unused-ignore"

from __future__ import annotations

from typing import Any

from typer.testing import CliRunner

from ssm_explorer.config import AppConfig
from ssm_explorer.main import app
from ssm_explorer.models.parameter import (
    DiffStatus,
    ParameterType,
    SearchResult,
    SSMParameter,
)

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
        if path == "/b-only-a":
            return SearchResult(
                path=path,
                parameters=[
                    SSMParameter(
                        name="/myapp/common/API_URL",
                        value="same",
                        type=ParameterType.STRING,
                    ),
                ],
                profile=self.profile,
                region=self.region,
            )
        if path == "/b-only-b":
            return SearchResult(
                path=path,
                parameters=[
                    SSMParameter(
                        name="/myapp/common/API_URL",
                        value="same",
                        type=ParameterType.STRING,
                    ),
                    SSMParameter(
                        name="/myapp/b-only/B_ONLY_URL",
                        value="b-only",
                        type=ParameterType.STRING,
                    ),
                ],
                profile=self.profile,
                region=self.region,
            )
        values_by_region = {
            "eu-west-1": [
                SSMParameter(
                    name="/myapp/browser/API_URL",
                    value="west-browser",
                    type=ParameterType.STRING,
                ),
                SSMParameter(
                    name="/myapp/worker/WORKER_URL",
                    value="west-worker",
                    type=ParameterType.STRING,
                ),
            ],
            "eu-central-1": [
                SSMParameter(
                    name="/myapp/browser/API_URL",
                    value="central-browser",
                    type=ParameterType.STRING,
                ),
                SSMParameter(
                    name="/myapp/worker/WORKER_URL",
                    value="central-worker",
                    type=ParameterType.STRING,
                ),
            ],
        }
        return SearchResult(
            path=path,
            parameters=values_by_region[self.region],
            profile=self.profile,
            region=self.region,
        )


def test_diff_accepts_path_options_and_filter_path(monkeypatch):
    FakeSSMClient.calls = []
    captured: dict[str, Any] = {}

    def fake_render_diff_table(diffs, **kwargs):  # type: ignore[no-untyped-def]
        captured["diffs"] = diffs
        captured["kwargs"] = kwargs

    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.render_diff_table", fake_render_diff_table)
    monkeypatch.setattr(
        "ssm_explorer.commands.diff_cmd.cfg",
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
            "diff",
            "/",
            "--path-a",
            "/myapp",
            "--path-b",
            "/myapp",
            "--profile-a",
            "profile-a",
            "--region-a",
            "eu-west-1",
            "--profile-b",
            "profile-b",
            "--region-b",
            "eu-central-1",
            "--filter-path",
            "browser",
        ],
    )

    assert result.exit_code == 0, result.output
    assert [call["path"] for call in FakeSSMClient.calls] == ["/myapp", "/myapp"]

    diffs = captured["diffs"]
    assert len(diffs) == 1
    assert diffs[0].status == DiffStatus.CHANGED
    assert diffs[0].param_a.name == "/myapp/browser/API_URL"
    assert diffs[0].param_b.name == "/myapp/browser/API_URL"


def test_diff_still_accepts_positional_paths(monkeypatch):
    FakeSSMClient.calls = []

    def fake_render_diff_table(diffs, **kwargs):  # type: ignore[no-untyped-def]
        pass

    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.render_diff_table", fake_render_diff_table)
    monkeypatch.setattr(
        "ssm_explorer.commands.diff_cmd.cfg",
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
            "diff",
            "/source-a",
            "/source-b",
            "--profile-a",
            "profile-a",
            "--region-a",
            "eu-west-1",
            "--profile-b",
            "profile-b",
            "--region-b",
            "eu-central-1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert [call["path"] for call in FakeSSMClient.calls] == ["/source-a", "/source-b"]


def test_diff_accepts_shared_region_for_two_profiles(monkeypatch):
    FakeSSMClient.calls = []
    captured: dict[str, Any] = {}

    def fake_render_diff_table(diffs, **kwargs):  # type: ignore[no-untyped-def]
        captured["diffs"] = diffs

    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.render_diff_table", fake_render_diff_table)
    monkeypatch.setattr(
        "ssm_explorer.commands.diff_cmd.cfg",
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
            "diff",
            "/shared",
            "--profile-a",
            "profile-a",
            "--profile-b",
            "profile-b",
            "--region",
            "eu-central-1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert [call["profile"] for call in FakeSSMClient.calls] == ["profile-a", "profile-b"]
    assert [call["region"] for call in FakeSSMClient.calls] == ["eu-central-1", "eu-central-1"]
    assert [call["path"] for call in FakeSSMClient.calls] == ["/shared", "/shared"]
    assert [diff.status for diff in captured["diffs"]] == [
        DiffStatus.IDENTICAL,
        DiffStatus.IDENTICAL,
    ]


def test_diff_exc_identicals_filters_identical_rows(monkeypatch):
    FakeSSMClient.calls = []
    captured: dict[str, Any] = {}

    def fake_render_diff_table(diffs, **kwargs):  # type: ignore[no-untyped-def]
        captured["diffs"] = diffs

    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.render_diff_table", fake_render_diff_table)
    monkeypatch.setattr(
        "ssm_explorer.commands.diff_cmd.cfg",
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
            "diff",
            "/myapp",
            "--profile-a",
            "profile-a",
            "--region-a",
            "eu-west-1",
            "--profile-b",
            "profile-b",
            "--region-b",
            "eu-central-1",
            "--filter-path",
            "browser",
            "--exc-identicals",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(captured["diffs"]) == 1
    assert captured["diffs"][0].status == DiffStatus.CHANGED


def test_diff_exc_identicals_suppresses_render_when_all_rows_identical(monkeypatch):
    FakeSSMClient.calls = []
    captured: dict[str, Any] = {}

    def fake_render_diff_table(diffs, **kwargs):  # type: ignore[no-untyped-def]
        captured["diffs"] = diffs

    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.render_diff_table", fake_render_diff_table)
    monkeypatch.setattr(
        "ssm_explorer.commands.diff_cmd.cfg",
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
            "diff",
            "/shared",
            "--profile-a",
            "profile-a",
            "--profile-b",
            "profile-b",
            "--region",
            "eu-central-1",
            "--exc-identicals",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "All 2 parameters are IDENTICAL" in result.output
    assert "diffs" not in captured


def test_diff_includes_source_b_only_rows_by_default(monkeypatch):
    FakeSSMClient.calls = []
    captured: dict[str, Any] = {}

    def fake_render_diff_table(diffs, **kwargs):  # type: ignore[no-untyped-def]
        captured["diffs"] = diffs

    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.render_diff_table", fake_render_diff_table)
    monkeypatch.setattr(
        "ssm_explorer.commands.diff_cmd.cfg",
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
            "diff",
            "/b-only-a",
            "/b-only-b",
            "--profile-a",
            "profile-a",
            "--profile-b",
            "profile-b",
            "--region",
            "eu-west-1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert [diff.status for diff in captured["diffs"]] == [
        DiffStatus.IDENTICAL,
        DiffStatus.MISSING_IN_A,
    ]


def test_diff_exc_missing_a_filters_source_b_only_rows(monkeypatch):
    FakeSSMClient.calls = []
    captured: dict[str, Any] = {}

    def fake_render_diff_table(diffs, **kwargs):  # type: ignore[no-untyped-def]
        captured["diffs"] = diffs

    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.SSMClient", FakeSSMClient)
    monkeypatch.setattr("ssm_explorer.commands.diff_cmd.render_diff_table", fake_render_diff_table)
    monkeypatch.setattr(
        "ssm_explorer.commands.diff_cmd.cfg",
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
            "diff",
            "/b-only-a",
            "/b-only-b",
            "--profile-a",
            "profile-a",
            "--profile-b",
            "profile-b",
            "--region",
            "eu-west-1",
            "--exc-missing-a",
        ],
    )

    assert result.exit_code == 0, result.output
    assert [diff.status for diff in captured["diffs"]] == [DiffStatus.IDENTICAL]

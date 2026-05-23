"""Tests for the check command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ssm_explorer.main import app

runner = CliRunner()


class FakeBotocoreSession:
    def __init__(self, profiles: list[str] | None = None, regions: list[str] | None = None) -> None:
        self.available_profiles = profiles or ["prod"]
        self._regions = regions or ["eu-west-1"]

    def get_available_regions(self, service_name: str) -> list[str]:
        assert service_name == "ssm"
        return self._regions


def _write_config(tmp_path: Path, *, profile: str = "prod", region: str = "eu-west-1") -> Path:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        f'[aws]\nprofile = "{profile}"\nregion = "{region}"\n',
        encoding="utf-8",
    )
    return config_file


def test_check_passes_with_valid_profile_and_region(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_file = _write_config(tmp_path)

    monkeypatch.setattr(
        "ssm_explorer.commands.check_cmd.shutil.which", lambda _: "/bin/ssm-explorer"
    )
    monkeypatch.setattr(
        "ssm_explorer.commands.check_cmd.botocore.session.Session",
        lambda: FakeBotocoreSession(),
    )

    result = runner.invoke(app, ["check", "--config", str(config_file)])

    assert result.exit_code == 0, result.output
    assert "Ready:" in result.output
    assert "local AWS profile" in result.output


def test_check_fails_when_profile_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_file = _write_config(tmp_path)

    monkeypatch.setattr(
        "ssm_explorer.commands.check_cmd.shutil.which", lambda _: "/bin/ssm-explorer"
    )
    monkeypatch.setattr(
        "ssm_explorer.commands.check_cmd.botocore.session.Session",
        lambda: FakeBotocoreSession(profiles=["dev"]),
    )

    result = runner.invoke(app, ["check", "--config", str(config_file)])

    assert result.exit_code == 1, result.output
    assert "'prod' not found in local AWS config." in result.output

"""Tests for configuration resolution logic."""
# mypy: disable-error-code="no-untyped-def"

from __future__ import annotations

from pathlib import Path

import pytest

from ssm_explorer.config import AppConfig, _apply_env_overrides, resolve_config_path


def test_resolve_aws_uses_profile_specific_region():
    cfg = AppConfig.model_validate(
        {
            "aws": {
                "profile": "",
                "region": "",
                "profiles": {
                    "prod": {"region": "eu-west-1"},
                },
            }
        }
    )

    profile, region = cfg.resolve_aws("prod", None)
    assert profile == "prod"
    assert region == "eu-west-1"


def test_resolve_aws_requires_profile():
    cfg = AppConfig.model_validate({"aws": {"profile": "", "region": "eu-west-1"}})

    with pytest.raises(ValueError, match="AWS profile is required"):
        cfg.resolve_aws(None, None)


def test_resolve_aws_uses_env_tag_profile_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("Environment", "myapp-prod")
    cfg = AppConfig.model_validate(
        {
            "aws": {
                "profile": "",
                "region": "eu-west-1",
                "profile_from_env_tags": ["Environment", "APP_ENV"],
            }
        }
    )

    profile, region = cfg.resolve_aws(None, None)
    assert profile == "myapp-prod"
    assert region == "eu-west-1"


def test_resolve_aws_uses_profile_map_for_env_tag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("Environment", "myapp-prod")
    cfg = AppConfig.model_validate(
        {
            "aws": {
                "profile": "",
                "region": "eu-west-1",
                "profile_from_env_tags": ["Environment"],
                "profile_from_env_value_map": {"myapp-prod": "prod_account"},
            }
        }
    )

    profile, region = cfg.resolve_aws(None, None)
    assert profile == "prod_account"
    assert region == "eu-west-1"


def test_resolve_aws_uses_first_matching_env_tag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "dev_account")
    monkeypatch.setenv("Environment", "prod_account")
    cfg = AppConfig.model_validate(
        {
            "aws": {
                "profile": "",
                "region": "eu-west-1",
                "profile_from_env_tags": ["APP_ENV", "Environment"],
            }
        }
    )

    profile, _ = cfg.resolve_aws(None, None)
    assert profile == "dev_account"


def test_apply_env_overrides_parses_aws_profile_from_env_settings(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SSM_EXPLORER_AWS_PROFILE_FROM_ENV_TAGS", "Environment, APP_ENV")
    monkeypatch.setenv(
        "SSM_EXPLORER_AWS_PROFILE_FROM_ENV_VALUE_MAP",
        "myapp-prod=prod_account,myapp-dev=dev_account",
    )

    raw = _apply_env_overrides({})

    assert raw["aws"]["profile_from_env_tags"] == ["Environment", "APP_ENV"]
    assert raw["aws"]["profile_from_env_value_map"] == {
        "myapp-prod": "prod_account",
        "myapp-dev": "dev_account",
    }


def test_resolve_aws_requires_region():
    cfg = AppConfig.model_validate({"aws": {"profile": "prod", "region": ""}})

    with pytest.raises(ValueError, match="AWS region is required"):
        cfg.resolve_aws(None, None)


def test_resolve_aws_allows_cli_region_override():
    cfg = AppConfig.model_validate({"aws": {"profile": "prod", "region": "eu-west-1"}})

    profile, region = cfg.resolve_aws(None, "us-east-2")
    assert profile == "prod"
    assert region == "us-east-2"


def test_resolve_aws_uses_config_when_cli_not_given():
    cfg = AppConfig.model_validate({"aws": {"profile": "prod", "region": "eu-central-1"}})

    profile, region = cfg.resolve_aws(None, None)
    assert profile == "prod"
    assert region == "eu-central-1"


def test_resolve_aws_cli_profile_overrides_config_profile():
    cfg = AppConfig.model_validate(
        {
            "aws": {
                "profile": "prod",
                "region": "eu-central-1",
                "profiles": {"dev": {"region": "eu-west-1"}},
            }
        }
    )

    profile, region = cfg.resolve_aws("dev", None)
    assert profile == "dev"
    assert region == "eu-west-1"


def test_resolve_aws_cli_profile_does_not_inherit_mismatched_config_region():
    cfg = AppConfig.model_validate(
        {
            "aws": {"profile": "prod", "region": "eu-central-1"},
        }
    )

    with pytest.raises(ValueError, match="does not match aws.profile"):
        cfg.resolve_aws("dev", None)


def test_resolve_aws_cli_region_allows_mismatched_profile():
    cfg = AppConfig.model_validate(
        {
            "aws": {"profile": "prod", "region": "eu-central-1"},
        }
    )

    profile, region = cfg.resolve_aws("dev", "eu-west-1")

    assert profile == "dev"
    assert region == "eu-west-1"


def test_resolve_path_does_not_inherit_mismatched_config_default_path():
    cfg = AppConfig.model_validate(
        {
            "aws": {"profile": "prod", "region": "eu-central-1"},
            "search": {"default_path": "/prod/app"},
        }
    )

    assert cfg.resolve_path(None, "dev") == ""


def test_resolve_path_allows_profile_specific_default_path_for_cli_profile():
    cfg = AppConfig.model_validate(
        {
            "aws": {
                "profile": "prod",
                "region": "eu-central-1",
                "profiles": {
                    "dev": {
                        "region": "eu-west-1",
                        "default_path": "/dev/app",
                    },
                },
            },
            "search": {"default_path": "/prod/app"},
        }
    )

    assert cfg.resolve_path(None, "dev") == "/dev/app"


def test_defaults_for_profiles_use_builtins_when_profile_mismatches_config():
    cfg = AppConfig.model_validate(
        {
            "aws": {"profile": "prod", "region": "eu-central-1"},
            "search": {"decrypt": False, "fetch_workers": 8},
            "output": {"format": "json", "overwrite": True},
        }
    )

    defaults = cfg.defaults_for_profiles("dev")

    assert defaults.search.decrypt is True
    assert defaults.search.fetch_workers == 4
    assert defaults.output.format == "env"
    assert defaults.output.overwrite is False


def test_defaults_for_profiles_keep_config_for_profile_specific_entry():
    cfg = AppConfig.model_validate(
        {
            "aws": {
                "profile": "prod",
                "region": "eu-central-1",
                "profiles": {"dev": {"region": "eu-west-1"}},
            },
            "search": {"decrypt": False, "fetch_workers": 8},
        }
    )

    defaults = cfg.defaults_for_profiles("dev")

    assert defaults.search.decrypt is False
    assert defaults.search.fetch_workers == 8


def test_resolve_config_path_falls_back_to_local_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    local_cfg = tmp_path / "config.toml"
    local_cfg.write_text('[aws]\nprofile = "x"\nregion = "y"\n', encoding="utf-8")

    import ssm_explorer.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "DEFAULT_CONFIG_FILE", tmp_path / "missing.toml")
    monkeypatch.delenv("SSM_EXPLORER_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)

    resolved = resolve_config_path(None)
    assert resolved == local_cfg.resolve()


def test_display_column_visibility_defaults_and_overrides():
    default_cfg = AppConfig.model_validate({})
    assert default_cfg.display.show_env_variable is True
    assert default_cfg.display.show_value is True
    assert default_cfg.display.show_type is False
    assert default_cfg.display.show_full_path is True
    assert default_cfg.display.show_version is False
    assert default_cfg.display.show_last_modified is False

    custom_cfg = AppConfig.model_validate(
        {
            "display": {
                "show_env_variable": False,
                "show_value": False,
                "show_type": False,
                "show_full_path": False,
                "show_version": False,
                "show_last_modified": False,
                "show_arn": True,
            }
        }
    )
    assert custom_cfg.display.show_env_variable is False
    assert custom_cfg.display.show_value is False
    assert custom_cfg.display.show_type is False
    assert custom_cfg.display.show_full_path is False
    assert custom_cfg.display.show_version is False
    assert custom_cfg.display.show_last_modified is False


def test_display_requires_at_least_one_visible_column():
    with pytest.raises(ValueError, match="at least one visible table column"):
        AppConfig.model_validate(
            {
                "display": {
                    "show_env_variable": False,
                    "show_value": False,
                    "show_type": False,
                    "show_full_path": False,
                    "show_version": False,
                    "show_last_modified": False,
                    "show_arn": False,
                }
            }
        )


def test_search_fetch_defaults_are_quota_aware():
    cfg = AppConfig.model_validate({})

    assert cfg.search.fetch_strategy == "auto"
    assert cfg.search.fetch_workers == 4
    assert cfg.search.max_get_tps == 20
    assert cfg.search.max_describe_tps == 3


def test_search_fetch_strategy_validation():
    with pytest.raises(ValueError, match="search.fetch_strategy"):
        AppConfig.model_validate({"search": {"fetch_strategy": "cached"}})


def test_apply_env_overrides_parses_fetch_tuning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SSM_EXPLORER_SEARCH_FETCH_STRATEGY", "path")
    monkeypatch.setenv("SSM_EXPLORER_SEARCH_FETCH_WORKERS", "8")
    monkeypatch.setenv("SSM_EXPLORER_SEARCH_MAX_GET_TPS", "40")
    monkeypatch.setenv("SSM_EXPLORER_SEARCH_MAX_DESCRIBE_TPS", "10")

    raw = _apply_env_overrides({})

    assert raw["search"]["fetch_strategy"] == "path"
    assert raw["search"]["fetch_workers"] == 8
    assert raw["search"]["max_get_tps"] == 40
    assert raw["search"]["max_describe_tps"] == 10

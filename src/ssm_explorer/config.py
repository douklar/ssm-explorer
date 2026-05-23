"""
SSM Explorer — Application configuration.

Config is loaded in priority order (highest → lowest):
  1. CLI flags passed by the user at runtime
  2. TOML config file  (~/.config/ssm-explorer/config.toml by default,
                        or $SSM_EXPLORER_CONFIG env var)
     If the default XDG file is missing, ./config.toml is used when present.
  3. Environment variables  (SSM_EXPLORER_<SECTION>_<KEY>)
  4. Hardcoded defaults defined in this module

The config file is **never written or modified** by the tool itself
(except by the explicit  `ssm-explorer config init`  command).

All AWS operations performed by this tool are strictly READ-ONLY:
  - ssm:GetParameter
  - ssm:GetParameters
  - ssm:GetParametersByPath
  - ssm:DescribeParameters
No write, put, delete or modify operations are ever issued.
"""

from __future__ import annotations

import os
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Config file location helpers
# ---------------------------------------------------------------------------

_XDG_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
DEFAULT_CONFIG_DIR: Path = _XDG_CONFIG_HOME / "ssm-explorer"
DEFAULT_CONFIG_FILE: Path = DEFAULT_CONFIG_DIR / "config.toml"


def resolve_config_path(override: str | None = None) -> Path:
    """
    Return the active config file path.

    Priority:
      1. ``override`` argument  (from ``--config`` CLI flag)
      2. ``SSM_EXPLORER_CONFIG`` environment variable
      3. ``~/.config/ssm-explorer/config.toml``  (XDG default)
      4. ``./config.toml`` if XDG default is missing
    """
    if override:
        return Path(override).expanduser().resolve()
    env_val = os.environ.get("SSM_EXPLORER_CONFIG", "").strip()
    if env_val:
        return Path(env_val).expanduser().resolve()
    if DEFAULT_CONFIG_FILE.exists():
        return DEFAULT_CONFIG_FILE
    local_default = (Path.cwd() / "config.toml").resolve()
    if local_default.exists():
        return local_default
    return DEFAULT_CONFIG_FILE


# ---------------------------------------------------------------------------
# Nested configuration models
# ---------------------------------------------------------------------------


class AWSProfileConfig(BaseModel):
    """Specific AWS profile configuration (e.g. binding a region to a profile)."""

    region: str
    default_path: str = Field(
        default="",
        description="Default SSM path for this specific profile.",
    )


class AWSConfig(BaseModel):
    """AWS connection settings."""

    profile: str = Field(
        default="",
        description=(
            "AWS named profile (from ~/.aws/config or ~/.aws/credentials). "
            "Leave empty to require explicit --profile."
        ),
    )
    region: str = Field(
        default="",
        description=(
            "AWS region name (e.g. eu-west-1, us-east-1). "
            "Leave empty to require explicit --region or profile-specific mapping."
        ),
    )
    profiles: dict[str, AWSProfileConfig] = Field(
        default_factory=dict,
        description="Region defaults for specific AWS profiles.",
    )
    profile_from_env_tags: list[str] = Field(
        default_factory=list,
        description=(
            "Environment variable names checked for AWS profile fallback. "
            "First non-empty value is used as profile when --profile/aws.profile are unset."
        ),
    )
    profile_from_env_value_map: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Optional mapping from environment tag value to AWS profile name. "
            "If key is not mapped, raw tag value is used as profile."
        ),
    )


class SearchConfig(BaseModel):
    """Default search / fetch behaviour."""

    default_path: str = Field(
        default="",
        description=(
            "Default SSM path prefix used when PATH argument is omitted. "
            "Must start with '/' if set (e.g. /my/app/prod)."
        ),
    )
    recursive: bool = Field(
        default=True,
        description="Recursively include all sub-paths by default.",
    )
    decrypt: bool = Field(
        default=True,
        description="Whether to decrypt SecureString values automatically.",
    )
    fetch_strategy: str = Field(
        default="auto",
        description=(
            "Fetch strategy: 'path' uses GetParametersByPath only; "
            "'batch' uses DescribeParameters plus parallel GetParameters; "
            "'auto' tries batch and falls back to path if IAM denies batch APIs."
        ),
    )
    fetch_workers: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Parallel workers for batched GetParameters calls.",
    )
    max_get_tps: int = Field(
        default=20,
        ge=1,
        le=1000,
        description=(
            "Client-side TPS cap for GetParameter/GetParameters calls. "
            "Default stays below AWS Parameter Store's 40 TPS standard quota."
        ),
    )
    max_describe_tps: int = Field(
        default=3,
        ge=1,
        le=10,
        description=(
            "Client-side TPS cap for DescribeParameters calls. "
            "Default matches AWS Parameter Store's standard quota."
        ),
    )

    @field_validator("default_path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if v and not v.startswith("/"):
            raise ValueError(f"search.default_path must start with '/'. Got: {v!r}")
        return v

    @field_validator("fetch_strategy")
    @classmethod
    def validate_fetch_strategy(cls, v: str) -> str:
        if v not in ("auto", "path", "batch"):
            raise ValueError(
                f"search.fetch_strategy must be 'auto', 'path', or 'batch'. Got: {v!r}"
            )
        return v


class DisplayConfig(BaseModel):
    """Terminal display preferences."""

    conceal: bool = Field(
        default=True,
        description=(
            "Conceal SecureString values: show first 4 chars + **** + char count. "
            "Set to false (or use --no-conceal) to reveal full values."
        ),
    )
    show_arn: bool = Field(
        default=False,
        description="Include the ARN column in table output.",
    )
    show_full_path: bool = Field(
        default=True,
        description="Include full parameter path/name column in table output.",
    )
    show_env_variable: bool = Field(
        default=True,
        description="Include ENV variable name column in table output.",
    )
    show_value: bool = Field(
        default=True,
        description="Include parameter value column in table output.",
    )
    show_type: bool = Field(
        default=False,
        description="Include parameter type column in table output.",
    )
    show_version: bool = Field(
        default=False,
        description="Include parameter version column in table output.",
    )
    show_last_modified: bool = Field(
        default=False,
        description="Include last modified date column in table output.",
    )
    max_value_length: int = Field(
        default=80,
        ge=10,
        le=500,
        description="Maximum characters to display in the Value column (10–500).",
    )

    @model_validator(mode="after")
    def validate_visible_columns(self) -> DisplayConfig:
        if not any(
            (
                self.show_env_variable,
                self.show_full_path,
                self.show_value,
                self.show_type,
                self.show_version,
                self.show_last_modified,
                self.show_arn,
            )
        ):
            raise ValueError("display must enable at least one visible table column.")
        return self


class FilterConfig(BaseModel):
    """Interactive live-filter browser preferences."""

    enabled: bool = Field(
        default=True,
        description="Allow the interactive browse/filter command.",
    )
    default_mode: str = Field(
        default="name",
        description="Default filter mode for the browser: 'name' or 'value'.",
    )

    @field_validator("default_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("name", "value"):
            raise ValueError(f"filter.default_mode must be 'name' or 'value'. Got: {v!r}")
        return v


class OutputConfig(BaseModel):
    """
    Output / save settings.

    File saving is **opt-in and disabled by default**.  The tool is
    READ-ONLY with respect to AWS; saving to a local file is the only
    write operation permitted, and only when ``save = true``.
    """

    save: bool = Field(
        default=False,
        description=(
            "Enable saving command output to a local file. MUST be true for --output-file to work."
        ),
    )
    path: str = Field(
        default="",
        description=(
            "Default output file path when save = true. "
            "Can be overridden per-run with --output-file."
        ),
    )
    format: str = Field(
        default="env",
        description="Default export format: 'env' or 'json'.",
    )
    overwrite: bool = Field(
        default=False,
        description="Overwrite existing output file without prompting.",
    )

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if v not in ("env", "json"):
            raise ValueError(f"output.format must be 'env' or 'json'. Got: {v!r}")
        return v

    @model_validator(mode="after")
    def warn_save_without_path(self) -> OutputConfig:
        # Non-fatal: just a logical consistency note (path can come from CLI)
        return self


class SecurityConfig(BaseModel):
    """Local security settings."""

    in_memory_encryption: bool = Field(
        default=False,
        description=(
            "Enable in-memory encryption of fetched secrets to prevent "
            "plaintext exposure in RAM / swap space. Decrypted on-the-fly."
        ),
    )


# ---------------------------------------------------------------------------
# Root application config
# ---------------------------------------------------------------------------


class AppConfig(BaseModel):
    """
    Root configuration object.

    All sections are optional — missing sections fall back to defaults.
    """

    aws: AWSConfig = Field(default_factory=AWSConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    # ------------------------------------------------------------------ #
    # Read-only enforcement
    # ------------------------------------------------------------------ #

    def assert_save_permitted(self) -> None:
        """
        Raise RuntimeError if file saving is not enabled in the config.

        This is the single chokepoint that enforces the read-only default.
        All commands that write local files MUST call this first.
        """
        if not self.output.save:
            raise RuntimeError(
                "File output is disabled by default (output.save = false).\n"
                "To enable saving, set  save = true  in your config file:\n\n"
                "    [output]\n"
                "    save = true\n"
                '    path = "/your/default/output/path"  # optional\n\n'
                "Or run:  ssm-explorer config init  to create a starter config."
            )

    # ------------------------------------------------------------------ #
    # Convenience accessors (keep commands concise)
    # ------------------------------------------------------------------ #

    def resolve_aws(
        self, profile_override: str | None, region_override: str | None
    ) -> tuple[str, str]:
        """
        Resolve the final AWS profile and region.

        Priority:
          1. Explicit CLI overrides (--profile, --region)
          2. Config profile-specific region ([aws.profiles.<profile>])
          3. Base config [aws] profile/region defaults

        Base config defaults only apply when the resolved profile matches
        aws.profile, or when aws.profile is empty. This prevents commands from
        accidentally reusing one profile's region/path defaults with another
        CLI profile.
        """
        profile = (
            profile_override or self.aws.profile or self._resolve_profile_from_env_tags()
        ).strip()
        if not profile:
            raise ValueError(
                "AWS profile is required. Set --profile, aws.profile, "
                "or configure aws.profile_from_env_tags."
            )

        region = ""
        profile_config = self.aws.profiles.get(profile)
        if profile_config is not None:
            profile_region = profile_config.region.strip()
            if profile_region:
                region = profile_region

        if not region and self._profile_matches_global_defaults(profile):
            region = self.aws.region.strip()

        # CLI region flag overrides everything
        if region_override:
            region = region_override.strip()

        if not region:
            if not self._profile_matches_global_defaults(profile):
                raise ValueError(
                    f"AWS region is required because profile '{profile}' does not match "
                    f"aws.profile '{self.aws.profile}'. Set --region or add "
                    f"aws.profiles.{profile}.region."
                )
            raise ValueError(
                "AWS region is required. Set --region, aws.region, "
                f"or aws.profiles.{profile}.region."
            )

        return profile, region

    def _profile_matches_global_defaults(self, profile_name: str) -> bool:
        """Return true when global config defaults are safe for this profile."""
        configured_profile = self.aws.profile.strip()
        return not configured_profile or configured_profile == profile_name

    def profile_uses_config_defaults(self, profile_name: str) -> bool:
        """Return true when this profile has matching global or profile-specific config."""
        return (
            self._profile_matches_global_defaults(profile_name) or profile_name in self.aws.profiles
        )

    def defaults_for_profiles(self, *profile_names: str) -> AppConfig:
        """
        Return this config only when all profiles are represented by it.

        When any CLI profile is outside the config, commands fall back to
        built-in defaults for non-CLI settings instead of borrowing another
        profile's config.
        """
        if all(self.profile_uses_config_defaults(profile_name) for profile_name in profile_names):
            return self
        return AppConfig()

    def _resolve_profile_from_env_tags(self) -> str:
        """
        Resolve AWS profile from configured environment tag variables.

        The first configured env key with a non-empty value wins.
        """
        for env_key in self.aws.profile_from_env_tags:
            key = env_key.strip()
            if not key:
                continue
            env_val = os.environ.get(key, "").strip()
            if env_val:
                return self.aws.profile_from_env_value_map.get(env_val, env_val)
        return ""

    def resolve_path(self, path_arg: str | None, profile_name: str) -> str:
        """
        Resolve the final SSM search path.

        Priority:
          1. Explicit CLI argument
          2. Profile-specific default_path ([aws.profiles.<profile>])
          3. Global search.default_path
        """
        if path_arg:
            return path_arg

        if profile_name in self.aws.profiles:
            prof_path = self.aws.profiles[profile_name].default_path
            if prof_path:
                return prof_path

        if not self._profile_matches_global_defaults(profile_name):
            return ""

        return self.search.default_path

    @property
    def profile(self) -> str:
        return self.aws.profile

    @property
    def region(self) -> str:
        return self.aws.region

    @property
    def default_path(self) -> str:
        return self.search.default_path

    @property
    def recursive(self) -> bool:
        return self.search.recursive

    @property
    def decrypt(self) -> bool:
        return self.search.decrypt

    @property
    def fetch_strategy(self) -> str:
        return self.search.fetch_strategy

    @property
    def fetch_workers(self) -> int:
        return self.search.fetch_workers

    @property
    def max_get_tps(self) -> int:
        return self.search.max_get_tps

    @property
    def max_describe_tps(self) -> int:
        return self.search.max_describe_tps

    @property
    def conceal(self) -> bool:
        return self.display.conceal

    @property
    def show_arn(self) -> bool:
        return self.display.show_arn

    @property
    def max_value_length(self) -> int:
        return self.display.max_value_length

    @property
    def show_full_path(self) -> bool:
        return self.display.show_full_path

    @property
    def show_env_variable(self) -> bool:
        return self.display.show_env_variable

    @property
    def show_value(self) -> bool:
        return self.display.show_value

    @property
    def show_type(self) -> bool:
        return self.display.show_type

    @property
    def show_version(self) -> bool:
        return self.display.show_version

    @property
    def show_last_modified(self) -> bool:
        return self.display.show_last_modified

    @property
    def filter_enabled(self) -> bool:
        return self.filter.enabled


# ---------------------------------------------------------------------------
# TOML loader & writer
# ---------------------------------------------------------------------------


def _dump_toml(data: dict[str, Any]) -> str:
    """Minimal TOML serializer for our flat-section dict structure, plus nested envs."""
    lines = [
        "# SSM Explorer — Configuration File",
        "# Auto-updated by: ssm-explorer config set",
        "",
    ]
    for section, values in data.items():
        lines.append(f"[{section}]")
        nested_dicts = {}
        for k, v in values.items():
            if isinstance(v, dict):
                nested_dicts[k] = v
                continue
            if isinstance(v, bool):
                val_str = "true" if v else "false"
            elif isinstance(v, int):
                val_str = str(v)
            else:
                val_safe = str(v).replace("\\", "\\\\").replace('"', '\\"')
                val_str = f'"{val_safe}"'
            lines.append(f"{k} = {val_str}")
        lines.append("")

        for nested_key, nested_val in nested_dicts.items():
            for sub_key, sub_val in nested_val.items():
                lines.append(f"[{section}.{nested_key}.{sub_key}]")
                for sk, sv in sub_val.items():
                    if isinstance(sv, bool):
                        val_str = "true" if sv else "false"
                    elif isinstance(sv, int):
                        val_str = str(sv)
                    else:
                        val_safe = str(sv).replace("\\", "\\\\").replace('"', '\\"')
                        val_str = f'"{val_safe}"'
                    lines.append(f"{sk} = {val_str}")
                lines.append("")
    return "\n".join(lines)


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Save the configuration to the TOML file."""
    if path is None:
        path = resolve_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    toml_str = _dump_toml(config.model_dump())
    path.write_text(toml_str, encoding="utf-8")


def _load_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file and return its content as a dict, or {} if missing."""
    if not path.exists():
        return {}
    try:
        with path.open("rb") as fh:
            result: dict[str, Any] = tomllib.load(fh)
            return result
    except (OSError, tomllib.TOMLDecodeError) as exc:
        # Surface the error so the user can fix their config file
        raise ValueError(
            f"Failed to read config file '{path}': {exc}\n"
            "Run  ssm-explorer config init  to regenerate a valid config."
        ) from exc


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """
    Overlay environment variables onto the raw TOML dict.

    Supported vars (all optional):
      SSM_EXPLORER_AWS_PROFILE
      SSM_EXPLORER_AWS_REGION
      SSM_EXPLORER_SEARCH_DEFAULT_PATH
      SSM_EXPLORER_SEARCH_RECURSIVE      (true/false)
      SSM_EXPLORER_SEARCH_DECRYPT        (true/false)
      SSM_EXPLORER_SEARCH_FETCH_STRATEGY (auto/path/batch)
      SSM_EXPLORER_SEARCH_FETCH_WORKERS  (integer)
      SSM_EXPLORER_SEARCH_MAX_GET_TPS    (integer)
      SSM_EXPLORER_SEARCH_MAX_DESCRIBE_TPS (integer)
      SSM_EXPLORER_DISPLAY_CONCEAL       (true/false)
      SSM_EXPLORER_DISPLAY_SHOW_ARN      (true/false)
      SSM_EXPLORER_DISPLAY_SHOW_FULL_PATH (true/false)
      SSM_EXPLORER_DISPLAY_SHOW_ENV_VARIABLE (true/false)
      SSM_EXPLORER_DISPLAY_SHOW_VALUE    (true/false)
      SSM_EXPLORER_DISPLAY_SHOW_TYPE     (true/false)
      SSM_EXPLORER_DISPLAY_SHOW_VERSION  (true/false)
      SSM_EXPLORER_DISPLAY_SHOW_LAST_MODIFIED (true/false)
      SSM_EXPLORER_DISPLAY_MAX_VALUE_LENGTH (integer)
      SSM_EXPLORER_FILTER_ENABLED        (true/false)
      SSM_EXPLORER_FILTER_DEFAULT_MODE   (name/value)
      SSM_EXPLORER_OUTPUT_SAVE           (true/false)
      SSM_EXPLORER_OUTPUT_PATH
      SSM_EXPLORER_OUTPUT_FORMAT         (env/json)
      SSM_EXPLORER_OUTPUT_OVERWRITE      (true/false)
    """

    def _bool(v: str) -> bool:
        return v.strip().lower() in ("1", "true", "yes", "on")

    def _set(section: str, key: str, val: str, cast: type = str) -> None:
        data.setdefault(section, {})
        if cast is bool:
            data[section][key] = _bool(val)
        elif cast is int:
            data[section][key] = int(val)
        else:
            data[section][key] = val

    mapping: list[tuple[str, str, str, type]] = [
        ("SSM_EXPLORER_AWS_PROFILE", "aws", "profile", str),
        ("SSM_EXPLORER_AWS_REGION", "aws", "region", str),
        ("SSM_EXPLORER_SEARCH_DEFAULT_PATH", "search", "default_path", str),
        ("SSM_EXPLORER_SEARCH_RECURSIVE", "search", "recursive", bool),
        ("SSM_EXPLORER_SEARCH_DECRYPT", "search", "decrypt", bool),
        ("SSM_EXPLORER_SEARCH_FETCH_STRATEGY", "search", "fetch_strategy", str),
        ("SSM_EXPLORER_SEARCH_FETCH_WORKERS", "search", "fetch_workers", int),
        ("SSM_EXPLORER_SEARCH_MAX_GET_TPS", "search", "max_get_tps", int),
        ("SSM_EXPLORER_SEARCH_MAX_DESCRIBE_TPS", "search", "max_describe_tps", int),
        ("SSM_EXPLORER_DISPLAY_CONCEAL", "display", "conceal", bool),
        ("SSM_EXPLORER_DISPLAY_SHOW_ARN", "display", "show_arn", bool),
        ("SSM_EXPLORER_DISPLAY_SHOW_FULL_PATH", "display", "show_full_path", bool),
        ("SSM_EXPLORER_DISPLAY_SHOW_ENV_VARIABLE", "display", "show_env_variable", bool),
        ("SSM_EXPLORER_DISPLAY_SHOW_VALUE", "display", "show_value", bool),
        ("SSM_EXPLORER_DISPLAY_SHOW_TYPE", "display", "show_type", bool),
        ("SSM_EXPLORER_DISPLAY_SHOW_VERSION", "display", "show_version", bool),
        ("SSM_EXPLORER_DISPLAY_SHOW_LAST_MODIFIED", "display", "show_last_modified", bool),
        ("SSM_EXPLORER_DISPLAY_MAX_VALUE_LENGTH", "display", "max_value_length", int),
        ("SSM_EXPLORER_FILTER_ENABLED", "filter", "enabled", bool),
        ("SSM_EXPLORER_FILTER_DEFAULT_MODE", "filter", "default_mode", str),
        ("SSM_EXPLORER_OUTPUT_SAVE", "output", "save", bool),
        ("SSM_EXPLORER_OUTPUT_PATH", "output", "path", str),
        ("SSM_EXPLORER_OUTPUT_FORMAT", "output", "format", str),
        ("SSM_EXPLORER_OUTPUT_OVERWRITE", "output", "overwrite", bool),
    ]
    for env_key, section, field, cast in mapping:
        val = os.environ.get(env_key, "").strip()
        if val:
            _set(section, field, val, cast)

    env_tags = os.environ.get("SSM_EXPLORER_AWS_PROFILE_FROM_ENV_TAGS", "").strip()
    if env_tags:
        parsed_tags = [v.strip() for v in env_tags.split(",") if v.strip()]
        data.setdefault("aws", {})
        data["aws"]["profile_from_env_tags"] = parsed_tags

    env_map = os.environ.get("SSM_EXPLORER_AWS_PROFILE_FROM_ENV_VALUE_MAP", "").strip()
    if env_map:
        parsed_map: dict[str, str] = {}
        for entry in env_map.split(","):
            item = entry.strip()
            if not item:
                continue
            if "=" not in item:
                continue
            k, v = item.split("=", 1)
            key = k.strip()
            val = v.strip()
            if key and val:
                parsed_map[key] = val
        if parsed_map:
            data.setdefault("aws", {})
            data["aws"]["profile_from_env_value_map"] = parsed_map

    return data


def load_config(config_path_override: str | None = None) -> AppConfig:
    """
    Load and return the application configuration.

    Merges TOML file + environment variables, then validates with Pydantic.

    Args:
        config_path_override: Explicit path to a config file (e.g. from
                              ``--config`` CLI flag).  If None, uses the
                              default XDG location or $SSM_EXPLORER_CONFIG.

    Returns:
        Validated AppConfig instance.
    """
    path = resolve_config_path(config_path_override)
    raw = _load_toml(path)
    raw = _apply_env_overrides(raw)
    return AppConfig.model_validate(raw)


# ---------------------------------------------------------------------------
# Default config template
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_TEMPLATE = """\
# SSM Explorer — Configuration File
# Generated by: ssm-explorer config init
#
# Edit this file to set your personal defaults.
# All settings can be overridden at runtime with CLI flags.
# Priority: CLI flags > this file > environment variables > built-in defaults
#
# READ-ONLY NOTICE
# This tool only ever reads from AWS SSM Parameter Store.
# Read APIs may include GetParameter, GetParameters, GetParametersByPath,
# and DescribeParameters depending on search.fetch_strategy.
# No write, put, delete or modify operations are performed on AWS.
# The only local write allowed is saving output to a file (output.save below).

# ── AWS Connection ────────────────────────────────────────────────────────────
[aws]

# AWS named profile from ~/.aws/config or ~/.aws/credentials.
# Override with: --profile my_profile_aws
# Leave empty ("") to require explicit --profile.
profile = ""

# AWS region. Override with: --region eu-west-1
# Leave empty ("") to require explicit --region or profile mapping.
region = ""

# Optional: detect profile from env tags (first non-empty key wins).
# Example: if Environment=myapp-prod, profile resolves to "myapp-prod".
# profile_from_env_tags = ["Environment", "APP_ENV", "ENVIRONMENT"]
#
# Optional mapping when env value and profile name differ:
# [aws.profile_from_env_value_map]
# myapp-prod = "prod_account"
# myapp-staging = "stage_account"

# You can bind specific regions to specific AWS profiles.
# If you use `--profile prod_account`, it will automatically use `eu-west-1`.
# [aws.profiles.prod_account]
# region = "eu-west-1"
#
# [aws.profiles.dev_account]
# region = "us-east-2"


# ── Search Defaults ───────────────────────────────────────────────────────────
[search]

# Default path prefix. When set, you can omit the PATH argument.
# Must start with '/'.  Example: "/my/app/production"
# Leave empty ("") to require PATH on every command.
default_path = ""

# Recursively include all sub-paths by default.
# Override with: --recursive / --no-recursive
recursive = true

# Decrypt SecureString values by default.
# Override with: --decrypt / --no-decrypt
# NOTE: Requires ssm:GetParameter with decryption IAM permission.
decrypt = true

# Fetch strategy:
#   auto  = faster batched fetch first; falls back to path fetch if IAM denies it
#   path  = original GetParametersByPath-only behavior
#   batch = DescribeParameters names + parallel GetParameters values
fetch_strategy = "auto"

# Batched fetch tuning. Defaults stay under AWS standard Parameter Store quotas:
# GetParameter/GetParameters/GetParametersByPath share 40 TPS; DescribeParameters is 3 TPS.
fetch_workers = 4
max_get_tps = 20
max_describe_tps = 3


# ── Display Preferences ───────────────────────────────────────────────────────
[display]

# Conceal SecureString values:  show first 4 chars + **** + (N chars).
# Set false (or use --no-conceal) to display full values.
# Only applies when decrypt = true.
conceal = true

# Show the full ARN column in table output.
show_arn = false

# Show full parameter path in table output.
show_full_path = true

# Show ENV variable name in table output.
show_env_variable = true

# Show value in table output.
show_value = true

# Show type in table output.
show_type = false

# Show parameter version in table output.
show_version = false

# Show last modified date in table output.
show_last_modified = false

# Maximum characters to show in the Value column (table view).
# Range: 10–500
max_value_length = 80


# ── Interactive Filter Browser ────────────────────────────────────────────────
[filter]

# Allow the interactive live-filter browser (ssm-explorer browse).
enabled = true

# Default filter mode when the browser opens: "name" or "value".
# Press Tab inside the browser to toggle at any time.
default_mode = "name"


# ── Output / File Saving ──────────────────────────────────────────────────────
[output]

# Master switch: set to true to allow saving output to a local file.
# When false (default), --output-file is ignored and no files are written.
# This is the READ-ONLY default — enable only when you need file exports.
save = false

# Default output file path when save = true.
# Can be overridden per-run with: --output-file /path/to/file
# Leave empty ("") to require --output-file on every export.
path = ""

# Default export format: "env" (dotenv file) or "json".
# Override with: --format env|json
format = "env"

# Overwrite the output file if it already exists.
# Override with: --overwrite / --no-overwrite
overwrite = false


# ── Local Security ────────────────────────────────────────────────────────────
[security]

# Enable in-memory encryption of fetched secrets to prevent plaintext
# exposure in RAM or swap space. Values are decrypted on-the-fly.
in_memory_encryption = false
"""


# ---------------------------------------------------------------------------
# Module-level singleton  (lazy-loaded on first import of this module)
# ---------------------------------------------------------------------------

# This is the default instance used by all commands.
# Commands that receive a --config flag should call load_config(path) instead
# and use the returned object directly.
cfg: AppConfig = load_config()

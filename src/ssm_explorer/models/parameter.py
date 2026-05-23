"""
Pydantic data models for SSM Parameter Store parameters.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, field_validator

# ---------------------------------------------------------------------------
# Transient in-memory encryption helper
# ---------------------------------------------------------------------------

_TRANSIENT_KEY = secrets.token_bytes(32)


def _xor_crypt(data: str) -> bytes:
    """XORs string data with the transient key, repeating the key if necessary."""
    b_data = data.encode("utf-8")
    return bytes(b ^ _TRANSIENT_KEY[i % len(_TRANSIENT_KEY)] for i, b in enumerate(b_data))


def _xor_decrypt(data: bytes) -> str:
    """Decrypts XOR encrypted bytes back to a UTF-8 string."""
    b_data = bytes(b ^ _TRANSIENT_KEY[i % len(_TRANSIENT_KEY)] for i, b in enumerate(data))
    return b_data.decode("utf-8")


# ---------------------------------------------------------------------------
# Concealment helper
# ---------------------------------------------------------------------------

_CONCEAL_PREFIX_LEN = 4  # how many chars to reveal at the start


def _conceal_value(value: str) -> str:
    """
    Partially mask a sensitive value.

    Shows the first ``_CONCEAL_PREFIX_LEN`` characters followed by ``****``
    and the total character count.  If the value is shorter than the prefix
    length, the whole value is replaced with ``****``.

    Examples::

        _conceal_value("super-secret-password")  # → 'supe****  (21 chars)'
        _conceal_value("abc")                    # → '****  (3 chars)'
    """
    total = len(value)
    if total <= _CONCEAL_PREFIX_LEN:
        return f"****  ({total} chars)"
    prefix = value[:_CONCEAL_PREFIX_LEN]
    return f"{prefix}****  ({total} chars)"



class ParameterType(str, Enum):
    """AWS SSM Parameter types."""

    STRING = "String"
    STRING_LIST = "StringList"
    SECURE_STRING = "SecureString"


class SSMParameter(BaseModel):
    """Represents a single SSM Parameter Store parameter."""

    name: str = Field(..., description="Full parameter path/name")
    value: str = Field(..., description="Parameter value (may be masked for SecureString)")
    type: ParameterType = Field(..., description="Parameter type")
    version: int = Field(default=1, description="Parameter version number")
    last_modified: datetime | None = Field(default=None, description="Last modification timestamp")
    arn: str | None = Field(default=None, description="Parameter ARN")
    data_type: str = Field(default="text", description="Data type (text, aws:ec2:image, etc.)")

    _value_enc: bytes | None = PrivateAttr(default=None)

    def model_post_init(self, __context: Any) -> None:
        encrypt = False
        try:
            from ssm_explorer.config import cfg
            encrypt = bool(cfg.security.in_memory_encryption)
        except Exception:
            pass
        if encrypt:
            object.__setattr__(self, "_value_enc", _xor_crypt(self.value))
            self.__dict__["value"] = "[ENCRYPTED_IN_MEMORY]"

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "value" and isinstance(value, str):
            encrypt = False
            try:
                from ssm_explorer.config import cfg
                encrypt = bool(cfg.security.in_memory_encryption)
            except Exception:
                pass
            if encrypt:
                object.__setattr__(self, "_value_enc", _xor_crypt(value))
                object.__setattr__(self, "value", "[ENCRYPTED_IN_MEMORY]")
                return
        super().__setattr__(name, value)

    def __getattribute__(self, name: str) -> Any:
        if name == "value":
            try:
                enc = object.__getattribute__(self, "_value_enc")
                if enc is not None:
                    return _xor_decrypt(enc)
            except AttributeError:
                pass
        return super().__getattribute__(name)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure parameter name starts with /."""
        if not v.startswith("/"):
            raise ValueError(f"Parameter name must start with '/'. Got: {v!r}")
        return v

    @property
    def env_variable_name(self) -> str:
        """Extract the environment variable name (last segment of the path)."""
        return self.name.rstrip("/").split("/")[-1]

    @property
    def parent_path(self) -> str:
        """Extract the parent path (everything except the last segment)."""
        parts = self.name.rstrip("/").split("/")
        return "/".join(parts[:-1]) or "/"

    @property
    def is_encrypted(self) -> bool:
        """Return True if this is a SecureString parameter."""
        return self.type == ParameterType.SECURE_STRING

    def display_value(
        self,
        decrypt: bool = False,
        conceal: bool = True,
        max_length: int | None = None,
    ) -> str:
        """
        Return a display-safe representation of the value.

        Concealment applies **only** to SecureString parameters and only when
        the value has actually been decrypted (i.e. ``decrypt=True``).
        If the value was never fetched in plaintext, we show the standard
        "not fetched" indicator instead.

        Concealment format:  ``ABCD****  (12 chars)``
          • First 4 characters are shown so you can identify the secret at a
            glance without exposing the full value.
          • The rest is replaced with ``****`` regardless of actual length.
          • Total character count is appended so you know the full size.

        Use ``--no-conceal`` (conceal=False) to display the complete value.
        """
        if self.is_encrypted and not decrypt:
            # Value was never decrypted — nothing to conceal, show hint
            display = "🔒 (SecureString — use --decrypt to fetch)"
        elif self.is_encrypted and decrypt and conceal:
            display = _conceal_value(self.value)
        else:
            display = self.value

        if max_length is not None and max_length > 0 and len(display) > max_length:
            return display[:max_length] + "…"

        return display

    def to_env_line(self) -> str:
        """Format as a .env file line: ENV_VAR=value."""
        # Wrap in quotes if value contains spaces or special characters
        value = self.value
        if " " in value or "=" in value or "#" in value:
            value = f'"{value}"'
        return f"{self.env_variable_name}={value}"

    def to_dict(self, conceal: bool = False) -> dict[str, str | int | bool | None]:
        """Serialize to a plain dict for JSON export.

        Args:
            conceal: If True and this is a SecureString, the value in the
                     dict will be the concealed representation rather than
                     the raw plaintext.  Defaults to False so that JSON
                     exports always contain full values (the caller already
                     decided to decrypt and export).
        """
        value = self.display_value(decrypt=True, conceal=conceal) if self.is_encrypted else self.value
        return {
            "name": self.name,
            "env_variable": self.env_variable_name,
            "value": value,
            "type": self.type.value,
            "version": self.version,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "arn": self.arn,
            "data_type": self.data_type,
        }


class SearchResult(BaseModel):
    """Container for a collection of SSM parameters returned from a search."""

    path: str = Field(..., description="The base path that was queried")
    parameters: list[SSMParameter] = Field(default_factory=list)
    total_count: int = Field(default=0, description="Total number of parameters found")
    profile: str = Field(default="default", description="AWS profile used")
    region: str = Field(default="us-east-1", description="AWS region queried")

    def model_post_init(self, __context: object) -> None:
        """Sync total_count with actual parameter count after init."""
        if self.total_count == 0 and self.parameters:
            self.total_count = len(self.parameters)

    def filter_by_name(self, pattern: str) -> SearchResult:
        """Return a new SearchResult filtered by case-insensitive name pattern."""
        pattern_lower = pattern.lower()
        filtered = [
            p for p in self.parameters if pattern_lower in p.env_variable_name.lower()
        ]
        return SearchResult(
            path=self.path,
            parameters=filtered,
            total_count=len(filtered),
            profile=self.profile,
            region=self.region,
        )

    def filter_by_value(self, pattern: str) -> SearchResult:
        """Return a new SearchResult filtered by case-insensitive value pattern."""
        pattern_lower = pattern.lower()
        filtered = [p for p in self.parameters if pattern_lower in p.value.lower()]
        return SearchResult(
            path=self.path,
            parameters=filtered,
            total_count=len(filtered),
            profile=self.profile,
            region=self.region,
        )

    def filter_by_path(self, pattern: str) -> SearchResult:
        """Return a new SearchResult filtered by case-insensitive full path pattern."""
        pattern_lower = pattern.lower()
        filtered = [p for p in self.parameters if pattern_lower in p.name.lower()]
        return SearchResult(
            path=self.path,
            parameters=filtered,
            total_count=len(filtered),
            profile=self.profile,
            region=self.region,
        )

    def to_env_file_content(self) -> str:
        """Generate the content of a .env file from all parameters."""
        header = f"# Generated by ssm-explorer from path: {self.path}\n"
        header += f"# Profile: {self.profile} | Region: {self.region}\n\n"
        lines = [p.to_env_line() for p in self.parameters]
        return header + "\n".join(lines) + "\n"

    def to_json_list(self) -> list[dict[str, str | int | bool | None]]:
        """Serialize all parameters to a list of dicts."""
        return [p.to_dict() for p in self.parameters]


# ---------------------------------------------------------------------------
# Diff models
# ---------------------------------------------------------------------------

class DiffStatus(str, Enum):
    """Status of a parameter comparison between two environments."""
    IDENTICAL = "IDENTICAL"       # Exists in both, values and types match
    CHANGED = "CHANGED"           # Exists in both, but value or type differs
    MISSING_IN_A = "MISSING_IN_A" # Exists in B, but not in A
    MISSING_IN_B = "MISSING_IN_B" # Exists in A, but not in B

class ParameterDiff(BaseModel):
    """Represents the difference of a single parameter across two environments."""
    env_variable: str
    status: DiffStatus
    param_a: SSMParameter | None = None
    param_b: SSMParameter | None = None

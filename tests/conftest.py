"""
Test fixtures and shared mocks for SSM Explorer test suite.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from ssm_explorer.models.parameter import ParameterType, SearchResult, SSMParameter

# ---------------------------------------------------------------------------
# Sample parameter factory helpers
# ---------------------------------------------------------------------------


def make_raw_param(
    name: str = "/test/path/MY_VAR",
    value: str = "hello-world",
    param_type: str = "String",
    version: int = 1,
) -> dict[str, object]:
    """Return a raw boto3-style parameter dict."""
    return {
        "Name": name,
        "Value": value,
        "Type": param_type,
        "Version": version,
        "LastModifiedDate": datetime(2024, 12, 1, 12, 0, 0, tzinfo=timezone.utc),
        "ARN": f"arn:aws:ssm:us-east-1:123456789012:parameter{name}",
        "DataType": "text",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_string_param() -> SSMParameter:
    return SSMParameter(
        name="/test/path/DATABASE_URL",
        value="postgres://localhost:5432/mydb",
        type=ParameterType.STRING,
        version=3,
        last_modified=datetime(2024, 12, 1, tzinfo=timezone.utc),
        arn="arn:aws:ssm:us-east-1:123456789012:parameter/test/path/DATABASE_URL",
    )


@pytest.fixture
def sample_secure_param() -> SSMParameter:
    return SSMParameter(
        name="/test/path/API_KEY",
        value="super-secret-key",
        type=ParameterType.SECURE_STRING,
        version=1,
        last_modified=datetime(2024, 11, 30, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_search_result(
    sample_string_param: SSMParameter,
    sample_secure_param: SSMParameter,
) -> SearchResult:
    return SearchResult(
        path="/test/path",
        parameters=[sample_string_param, sample_secure_param],
        total_count=2,
        profile="test-profile",
        region="us-east-1",
    )


@pytest.fixture
def mock_boto3_session() -> Generator[tuple[MagicMock, MagicMock], None, None]:
    """Patch boto3.Session so no real AWS calls are made."""
    with patch("boto3.Session") as mock_session:
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client
        yield mock_session, mock_client

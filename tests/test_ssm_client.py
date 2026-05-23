"""Tests for SSMClient — all AWS calls are mocked."""
# mypy: disable-error-code="no-untyped-def"

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, ProfileNotFound

from ssm_explorer.aws.ssm_client import (
    SSMAccessDeniedError,
    SSMAuthError,
    SSMClient,
    SSMParameterNotFoundError,
)
from ssm_explorer.models.parameter import ParameterType


def _make_client_error(code: str, message: str = "Error") -> ClientError:
    """Helper to build a boto3 ClientError."""
    return ClientError(
        error_response={"Error": {"Code": code, "Message": message}},
        operation_name="GetParametersByPath",
    )


class TestSSMClientInit:
    def test_profile_not_found_raises_auth_error(self):
        with patch("boto3.Session", side_effect=ProfileNotFound(profile="bad-profile")):
            with pytest.raises(SSMAuthError, match="bad-profile"):
                SSMClient(profile="bad-profile", region="us-east-1")

    def test_pins_profile_in_botocore_session(self):
        with patch("botocore.session.Session") as mock_botocore_session, patch("boto3.Session") as mock_boto3_session:
            mock_boto3_session.return_value.client.return_value = MagicMock()

            SSMClient(profile="my-profile", region="eu-west-1")

            mock_botocore_session.assert_called_once_with(profile="my-profile")


class TestGetParametersByPath:
    def _make_client(self, mock_boto_client: MagicMock) -> SSMClient:
        """Create an SSMClient with a mocked boto3 client."""
        with patch("boto3.Session") as mock_session:
            mock_session.return_value.client.return_value = mock_boto_client
            return SSMClient(profile="test", region="us-east-1")

    def test_returns_empty_result_for_no_params(self):
        mock_boto = MagicMock()
        mock_paginator = MagicMock()
        mock_boto.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = iter([{"Parameters": []}])

        client = self._make_client(mock_boto)
        result = client.get_parameters_by_path("/empty/path")

        assert result.total_count == 0
        assert result.parameters == []

    def test_maps_parameters_correctly(self, make_raw_param):
        raw = make_raw_param(name="/test/MY_VAR", value="hello", param_type="String")
        mock_boto = MagicMock()
        mock_paginator = MagicMock()
        mock_boto.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = iter([{"Parameters": [raw]}])

        client = self._make_client(mock_boto)
        result = client.get_parameters_by_path("/test")

        assert result.total_count == 1
        param = result.parameters[0]
        assert param.name == "/test/MY_VAR"
        assert param.value == "hello"
        assert param.type == ParameterType.STRING

    def test_handles_multiple_pages(self, make_raw_param):
        raw1 = make_raw_param(name="/test/A", value="1")
        raw2 = make_raw_param(name="/test/B", value="2")
        mock_boto = MagicMock()
        mock_paginator = MagicMock()
        mock_boto.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = iter([
            {"Parameters": [raw1]},
            {"Parameters": [raw2]},
        ])

        client = self._make_client(mock_boto)
        result = client.get_parameters_by_path("/test")

        assert result.total_count == 2

    def test_batch_strategy_describes_names_and_fetches_values(self, make_raw_param):
        raws = [
            make_raw_param(name=f"/test/PARAM_{index:02d}", value=str(index))
            for index in range(12)
        ]
        mock_boto = MagicMock()
        mock_boto.describe_parameters.return_value = {
            "Parameters": [
                {
                    "Name": raw["Name"],
                    "Type": raw["Type"],
                    "Version": raw["Version"],
                    "LastModifiedDate": raw["LastModifiedDate"],
                    "ARN": raw["ARN"],
                    "DataType": raw["DataType"],
                }
                for raw in raws
            ]
        }
        mock_boto.get_parameters.side_effect = [
            {"Parameters": raws[:10], "InvalidParameters": []},
            {"Parameters": raws[10:], "InvalidParameters": []},
        ]

        client = self._make_client(mock_boto)
        result = client.get_parameters_by_path(
            "/test",
            strategy="batch",
        )

        assert result.total_count == 12
        assert [param.name for param in result.parameters] == [
            raw["Name"] for raw in raws
        ]
        mock_boto.describe_parameters.assert_called_once_with(
            ParameterFilters=[
                {
                    "Key": "Path",
                    "Option": "Recursive",
                    "Values": ["/test"],
                }
            ],
            MaxResults=50,
        )
        assert mock_boto.get_parameters.call_count == 2

    def test_auto_strategy_falls_back_to_path_when_batch_access_denied(self, make_raw_param):
        raw = make_raw_param(name="/test/A", value="1")
        mock_boto = MagicMock()
        mock_boto.describe_parameters.side_effect = _make_client_error("AccessDeniedException")
        mock_paginator = MagicMock()
        mock_boto.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = iter([{"Parameters": [raw]}])

        client = self._make_client(mock_boto)
        result = client.get_parameters_by_path("/test", strategy="auto")

        assert result.total_count == 1
        mock_boto.get_paginator.assert_called_once_with("get_parameters_by_path")

    def test_access_denied_raises_domain_error(self):
        mock_boto = MagicMock()
        mock_paginator = MagicMock()
        mock_boto.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.side_effect = _make_client_error("AccessDeniedException")

        client = self._make_client(mock_boto)
        with pytest.raises(SSMAccessDeniedError):
            client.get_parameters_by_path("/blocked/path")

    def test_expired_token_raises_auth_error(self):
        mock_boto = MagicMock()
        mock_paginator = MagicMock()
        mock_boto.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.side_effect = _make_client_error("ExpiredTokenException")

        client = self._make_client(mock_boto)
        with pytest.raises(SSMAuthError):
            client.get_parameters_by_path("/some/path")


class TestGetParameter:
    def _make_client(self, mock_boto_client: MagicMock) -> SSMClient:
        with patch("boto3.Session") as mock_session:
            mock_session.return_value.client.return_value = mock_boto_client
            return SSMClient(profile="test", region="us-east-1")

    def test_gets_single_parameter(self, make_raw_param):
        raw = make_raw_param(name="/test/MY_VAR", value="the-value")
        mock_boto = MagicMock()
        mock_boto.get_parameter.return_value = {"Parameter": raw}

        client = self._make_client(mock_boto)
        param = client.get_parameter("/test/MY_VAR")

        assert param.name == "/test/MY_VAR"
        assert param.value == "the-value"

    def test_parameter_not_found_raises_domain_error(self):
        mock_boto = MagicMock()
        err = ClientError(
            error_response={"Error": {"Code": "ParameterNotFound", "Message": "Not found"}},
            operation_name="GetParameter",
        )
        mock_boto.get_parameter.side_effect = err

        client = self._make_client(mock_boto)
        with pytest.raises(SSMParameterNotFoundError):
            client.get_parameter("/nonexistent")


# Expose make_raw_param as a fixture for the test class
@pytest.fixture
def make_raw_param():
    from tests.conftest import make_raw_param as _factory
    return _factory

"""
AWS SSM Parameter Store client wrapper.

Provides a clean, typed interface around boto3's SSM client with:
- Automatic pagination handling
- Pydantic model conversion
- Proper error handling and contextual error messages
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any, cast

import boto3
import botocore.session
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    ProfileNotFound,
)

from ssm_explorer.models.parameter import ParameterType, SearchResult, SSMParameter

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient as BotoSSMClient

logger = logging.getLogger(__name__)

_DESCRIBE_PAGE_SIZE = 50
_GET_PARAMETERS_BATCH_SIZE = 10
_FETCH_STRATEGIES = {"auto", "path", "batch"}


class SSMClientError(Exception):
    """Base exception for SSM client errors."""


class SSMAuthError(SSMClientError):
    """Raised when AWS authentication fails."""


class SSMAccessDeniedError(SSMClientError):
    """Raised when the IAM permissions are insufficient."""


class SSMParameterNotFoundError(SSMClientError):
    """Raised when a requested parameter does not exist."""


class _RateLimiter:
    """Small thread-safe limiter for AWS TPS quotas."""

    def __init__(self, calls_per_second: int) -> None:
        self._interval = 1.0 / max(calls_per_second, 1)
        self._lock = Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = monotonic()
            if now >= self._next_at:
                self._next_at = now + self._interval
                return

            delay = self._next_at - now
            self._next_at += self._interval

        sleep(delay)


class SSMClient:
    """
    High-level AWS SSM Parameter Store client.

    Wraps boto3 SSM client with typed responses, pagination, and
    consistent error handling.

    Usage:
        client = SSMClient(profile="my_profile_aws", region="eu-west-1")
        result = client.get_parameters_by_path("/my/path")
    """

    def __init__(
        self,
        profile: str,
        region: str,
        *,
        fetch_workers: int = 4,
        max_get_tps: int = 20,
        max_describe_tps: int = 3,
    ) -> None:
        """
        Initialise the SSM client.

        Args:
            profile: AWS named profile (from ~/.aws/config or ~/.aws/credentials).
            region: AWS region name (e.g. "us-east-1", "eu-west-1").
            fetch_workers: Parallel workers for batched value fetches.
            max_get_tps: Client-side TPS cap for GetParameter(s) APIs.
            max_describe_tps: Client-side TPS cap for DescribeParameters.

        Raises:
            SSMAuthError: If the profile does not exist or credentials are invalid.
        """
        self.profile = profile
        self.region = region
        self.fetch_workers = max(1, fetch_workers)
        self._get_rate_limiter = _RateLimiter(max_get_tps)
        self._describe_rate_limiter = _RateLimiter(max_describe_tps)
        self._client: BotoSSMClient = self._create_client()

    def _create_client(self) -> BotoSSMClient:
        """Create and return the boto3 SSM client."""
        try:
            # Enable boto3 to load SSO profiles and other credential processes from ~/.aws/config
            os.environ.setdefault("AWS_SDK_LOAD_CONFIG", "1")

            # Pin profile directly in botocore session to mirror `aws --profile <name>`
            # even when AWS_PROFILE/AWS_DEFAULT_PROFILE env vars are set differently.
            botocore_session = botocore.session.Session(profile=self.profile)
            session = boto3.Session(
                botocore_session=botocore_session,
                profile_name=self.profile,
                region_name=self.region,
            )
            return session.client(
                "ssm",
                config=Config(
                    max_pool_connections=max(10, self.fetch_workers + 2),
                    retries={"mode": "adaptive", "max_attempts": 10},
                ),
            )
        except ProfileNotFound as exc:
            raise SSMAuthError(
                f"AWS profile '{self.profile}' not found. "
                "Check your ~/.aws/config or ~/.aws/credentials file."
            ) from exc
        except NoCredentialsError as exc:
            raise SSMAuthError(
                "No AWS credentials found. Configure via 'aws configure' or environment variables."
            ) from exc

    def get_parameters_by_path(
        self,
        path: str,
        *,
        recursive: bool = True,
        decrypt: bool = False,
        strategy: str = "path",
    ) -> SearchResult:
        """
        Retrieve all parameters under the given path prefix.

        Handles full pagination automatically. The default `path` strategy uses
        GetParametersByPath. The `batch` strategy uses DescribeParameters to
        collect names, then parallel GetParameters calls for values. `auto`
        tries `batch` first and falls back to `path` if IAM lacks batch APIs.

        Args:
            path:       SSM parameter path prefix (must start with '/').
            recursive:  If True, includes all sub-paths recursively.
            decrypt:    If True, decrypts SecureString parameter values.
            strategy:   Fetch strategy: "path", "batch", or "auto".

        Returns:
            SearchResult containing all matching parameters.

        Raises:
            SSMAuthError:         On credential / profile errors.
            SSMAccessDeniedError: On insufficient IAM permissions.
            SSMClientError:       On other boto3/botocore errors.
        """
        if not path.startswith("/"):
            path = f"/{path}"
        if strategy not in _FETCH_STRATEGIES:
            raise ValueError(
                f"Unsupported fetch strategy '{strategy}'. Use one of: "
                f"{', '.join(sorted(_FETCH_STRATEGIES))}."
            )

        logger.debug(
            "Fetching parameters: path=%s recursive=%s decrypt=%s strategy=%s profile=%s region=%s",
            path,
            recursive,
            decrypt,
            strategy,
            self.profile,
            self.region,
        )

        if strategy in ("auto", "batch"):
            try:
                return self._get_parameters_by_path_batched(
                    path,
                    recursive=recursive,
                    decrypt=decrypt,
                )
            except SSMAccessDeniedError:
                if strategy == "batch":
                    raise
                logger.debug(
                    "Batch fetch is not permitted for profile=%s region=%s; falling back to GetParametersByPath.",
                    self.profile,
                    self.region,
                )

        return self._get_parameters_by_path_paginated(
            path,
            recursive=recursive,
            decrypt=decrypt,
        )

    def _get_parameters_by_path_paginated(
        self,
        path: str,
        *,
        recursive: bool,
        decrypt: bool,
    ) -> SearchResult:
        """Fetch parameters using GetParametersByPath pagination."""
        try:
            paginator = self._client.get_paginator("get_parameters_by_path")
            page_iterator = paginator.paginate(
                Path=path,
                Recursive=recursive,
                WithDecryption=decrypt,
                PaginationConfig={"PageSize": _GET_PARAMETERS_BATCH_SIZE},
            )

            raw_params: list[dict[str, Any]] = []
            for page in page_iterator:
                raw_params.extend(cast(list[dict[str, Any]], page.get("Parameters", [])))

        except ClientError as exc:
            self._handle_client_error(exc)
        except NoCredentialsError as exc:
            raise SSMAuthError(
                f"No AWS credentials found for profile '{self.profile}'.\n"
                "If using SSO, ensure you have run 'aws sso login' and that AWS_SDK_LOAD_CONFIG=1 is working.\n"
                "Check your ~/.aws/config or ~/.aws/credentials file."
            ) from exc
        except (BotoCoreError, Exception) as exc:
            raise SSMClientError(f"Unexpected error communicating with AWS SSM: {exc}") from exc

        parameters = [self._map_parameter(p, decrypted=decrypt) for p in raw_params]

        return SearchResult(
            path=path,
            parameters=parameters,
            total_count=len(parameters),
            profile=self.profile,
            region=self.region,
        )

    def _get_parameters_by_path_batched(
        self,
        path: str,
        *,
        recursive: bool,
        decrypt: bool,
    ) -> SearchResult:
        """
        Fetch parameter names in larger metadata pages, then fetch values in parallel.

        AWS docs cap DescribeParameters at 50 items and GetParameters at 10 names.
        Rate limiters keep this below default Parameter Store TPS quotas.
        """
        metadata = self._describe_parameters_by_path(path, recursive=recursive)
        names = sorted({str(item["Name"]) for item in metadata if item.get("Name")})
        if not names:
            return SearchResult(
                path=path,
                parameters=[],
                total_count=0,
                profile=self.profile,
                region=self.region,
            )

        raw_params = self._get_parameters_by_names(names, decrypt=decrypt)
        metadata_by_name = {str(item["Name"]): item for item in metadata if item.get("Name")}
        raw_by_name = {
            str(item["Name"]): {**metadata_by_name.get(str(item["Name"]), {}), **item}
            for item in raw_params
            if item.get("Name")
        }
        parameters = [
            self._map_parameter(raw_by_name[name], decrypted=decrypt)
            for name in names
            if name in raw_by_name
        ]

        return SearchResult(
            path=path,
            parameters=parameters,
            total_count=len(parameters),
            profile=self.profile,
            region=self.region,
        )

    def _describe_parameters_by_path(
        self,
        path: str,
        *,
        recursive: bool,
    ) -> list[dict[str, Any]]:
        """Return ParameterMetadata for all names under a path."""
        option = "Recursive" if recursive else "OneLevel"
        next_token: str | None = None
        parameters: list[dict[str, Any]] = []

        while True:
            request: dict[str, Any] = {
                "ParameterFilters": [
                    {
                        "Key": "Path",
                        "Option": option,
                        "Values": [path],
                    }
                ],
                "MaxResults": _DESCRIBE_PAGE_SIZE,
            }
            if next_token:
                request["NextToken"] = next_token

            try:
                self._describe_rate_limiter.wait()
                response = self._client.describe_parameters(**request)
            except ClientError as exc:
                self._handle_client_error(exc)
            except NoCredentialsError as exc:
                raise SSMAuthError(
                    f"No AWS credentials found for profile '{self.profile}'.\n"
                    "If using SSO, ensure you have run 'aws sso login' and that AWS_SDK_LOAD_CONFIG=1 is working.\n"
                    "Check your ~/.aws/config or ~/.aws/credentials file."
                ) from exc
            except (BotoCoreError, Exception) as exc:
                raise SSMClientError(f"Unexpected error communicating with AWS SSM: {exc}") from exc

            parameters.extend(cast(list[dict[str, Any]], response.get("Parameters", [])))
            next_token = response.get("NextToken")
            if not next_token:
                return parameters

    def _get_parameters_by_names(
        self,
        names: Sequence[str],
        *,
        decrypt: bool,
    ) -> list[dict[str, Any]]:
        """Fetch named parameters in parallel GetParameters batches."""
        chunks = list(self._chunks(names, _GET_PARAMETERS_BATCH_SIZE))
        if not chunks:
            return []

        raw_params: list[dict[str, Any]] = []
        workers = min(self.fetch_workers, len(chunks))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._get_parameters_batch, chunk, decrypt=decrypt)
                for chunk in chunks
            ]
            for future in as_completed(futures):
                raw_params.extend(future.result())
        return raw_params

    def _get_parameters_batch(
        self,
        names: Sequence[str],
        *,
        decrypt: bool,
    ) -> list[dict[str, Any]]:
        """Fetch one GetParameters batch."""
        try:
            self._get_rate_limiter.wait()
            response = self._client.get_parameters(
                Names=list(names),
                WithDecryption=decrypt,
            )
            invalid_count = len(response.get("InvalidParameters", []))
            if invalid_count:
                logger.debug(
                    "AWS SSM returned %s invalid parameter name(s) during batch fetch.",
                    invalid_count,
                )
            return cast(list[dict[str, Any]], response.get("Parameters", []))
        except ClientError as exc:
            self._handle_client_error(exc)
        except NoCredentialsError as exc:
            raise SSMAuthError(
                f"No AWS credentials found for profile '{self.profile}'.\n"
                "If using SSO, ensure you have run 'aws sso login' and that AWS_SDK_LOAD_CONFIG=1 is working.\n"
                "Check your ~/.aws/config or ~/.aws/credentials file."
            ) from exc
        except (BotoCoreError, Exception) as exc:
            raise SSMClientError(f"Unexpected error communicating with AWS SSM: {exc}") from exc

        raise SSMClientError("Unreachable")  # pragma: no cover

    @staticmethod
    def _chunks(items: Sequence[str], size: int) -> Iterator[list[str]]:
        for index in range(0, len(items), size):
            yield list(items[index : index + size])

    def get_parameter(
        self,
        name: str,
        *,
        decrypt: bool = False,
    ) -> SSMParameter:
        """
        Retrieve a single parameter by its exact name/path.

        Args:
            name:    Full parameter name (e.g. '/my/path/DATABASE_URL').
            decrypt: If True, decrypts SecureString values.

        Returns:
            SSMParameter object.

        Raises:
            SSMParameterNotFoundError: If the parameter does not exist.
            SSMAccessDeniedError:      On insufficient IAM permissions.
            SSMClientError:            On other errors.
        """
        if not name.startswith("/"):
            name = f"/{name}"

        logger.debug("Fetching single parameter: name=%s decrypt=%s", name, decrypt)

        try:
            self._get_rate_limiter.wait()
            response = self._client.get_parameter(
                Name=name,
                WithDecryption=decrypt,
            )
            return self._map_parameter(
                cast(dict[str, Any], response["Parameter"]),
                decrypted=decrypt,
            )

        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "ParameterNotFound":
                raise SSMParameterNotFoundError(
                    f"Parameter '{name}' does not exist in region '{self.region}'."
                ) from exc
            self._handle_client_error(exc)
        except NoCredentialsError as exc:
            raise SSMAuthError(
                f"No AWS credentials found for profile '{self.profile}'.\n"
                "If using SSO, ensure you have run 'aws sso login' and that AWS_SDK_LOAD_CONFIG=1 is working.\n"
                "Check your ~/.aws/config or ~/.aws/credentials file."
            ) from exc
        except (BotoCoreError, Exception) as exc:
            raise SSMClientError(f"Unexpected error: {exc}") from exc

        # Should never reach here, but satisfies mypy
        raise SSMClientError("Unreachable")  # pragma: no cover

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_parameter(raw: dict[str, Any], *, decrypted: bool) -> SSMParameter:  # noqa: ARG004
        """Convert a raw boto3 parameter dict to an SSMParameter model."""
        param_type = ParameterType(raw.get("Type", "String"))
        return SSMParameter(
            name=raw["Name"],
            value=raw.get("Value", ""),
            type=param_type,
            version=raw.get("Version", 1),
            last_modified=raw.get("LastModifiedDate"),
            arn=raw.get("ARN"),
            data_type=raw.get("DataType", "text"),
        )

    @staticmethod
    def _handle_client_error(exc: ClientError) -> None:
        """Translate boto3 ClientError into a domain-specific exception."""
        error_code = exc.response.get("Error", {}).get("Code", "")
        error_msg = exc.response.get("Error", {}).get("Message", str(exc))

        if error_code in ("AccessDeniedException", "AccessDenied"):
            raise SSMAccessDeniedError(
                f"Access denied. Ensure your IAM role/user has read permissions required "
                f"by the selected fetch strategy: "
                f"ssm:GetParameter, ssm:GetParameters, ssm:GetParametersByPath, "
                f"and ssm:DescribeParameters.\nAWS error: {error_msg}"
            ) from exc
        if error_code in ("ExpiredTokenException", "InvalidClientTokenId"):
            raise SSMAuthError(
                f"AWS credentials are expired or invalid. "
                f"Run 'aws sso login --profile <profile>' or refresh your session.\n"
                f"AWS error: {error_msg}"
            ) from exc

        raise SSMClientError(f"AWS SSM error [{error_code}]: {error_msg}") from exc

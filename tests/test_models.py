"""Tests for SSMParameter and SearchResult Pydantic models."""
# mypy: disable-error-code="no-untyped-def"

from __future__ import annotations

import pytest

from ssm_explorer.models.parameter import ParameterType, SearchResult, SSMParameter


class TestSSMParameter:
    def test_env_variable_name_extraction(self):
        param = SSMParameter(
            name="/my/path/to/var/DATABASE_URL",
            value="postgres://localhost/db",
            type=ParameterType.STRING,
        )
        assert param.env_variable_name == "DATABASE_URL"

    def test_env_variable_name_trailing_slash(self):
        param = SSMParameter(
            name="/my/path/REDIS_HOST/",
            value="localhost",
            type=ParameterType.STRING,
        )
        assert param.env_variable_name == "REDIS_HOST"

    def test_parent_path(self):
        param = SSMParameter(
            name="/my/path/to/var/DATABASE_URL",
            value="x",
            type=ParameterType.STRING,
        )
        assert param.parent_path == "/my/path/to/var"

    def test_is_encrypted_false_for_string(self):
        param = SSMParameter(name="/a/B", value="v", type=ParameterType.STRING)
        assert param.is_encrypted is False

    def test_is_encrypted_true_for_secure_string(self):
        param = SSMParameter(name="/a/B", value="secret", type=ParameterType.SECURE_STRING)
        assert param.is_encrypted is True

    def test_display_value_hint_when_not_decrypted(self):
        param = SSMParameter(name="/a/B", value="secret", type=ParameterType.SECURE_STRING)
        result = param.display_value(decrypt=False)
        assert "🔒" in result or "decrypt" in result.lower()

    def test_display_value_concealed_by_default_when_decrypted(self):
        param = SSMParameter(name="/a/B", value="super-secret", type=ParameterType.SECURE_STRING)
        result = param.display_value(decrypt=True, conceal=True)
        assert "****" in result
        assert "supe" in result          # first 4 chars visible
        assert "12 chars" in result      # char count

    def test_display_value_full_when_no_conceal(self):
        param = SSMParameter(name="/a/B", value="super-secret", type=ParameterType.SECURE_STRING)
        assert param.display_value(decrypt=True, conceal=False) == "super-secret"

    def test_display_value_short_secret_fully_masked(self):
        param = SSMParameter(name="/a/B", value="abc", type=ParameterType.SECURE_STRING)
        result = param.display_value(decrypt=True, conceal=True)
        assert "****" in result
        assert "abc" not in result       # too short to reveal prefix

    def test_display_value_plain_string_not_concealed(self):
        param = SSMParameter(name="/a/B", value="plaintext", type=ParameterType.STRING)
        assert param.display_value(decrypt=False, conceal=True) == "plaintext"

    def test_display_value_supports_max_length_truncation(self):
        param = SSMParameter(name="/a/B", value="abcdefghij", type=ParameterType.STRING)
        assert param.display_value(decrypt=True, conceal=False, max_length=5) == "abcde…"

    def test_to_env_line_simple(self):
        param = SSMParameter(name="/a/MY_VAR", value="hello", type=ParameterType.STRING)
        assert param.to_env_line() == "MY_VAR=hello"

    def test_to_env_line_quotes_spaces(self):
        param = SSMParameter(name="/a/MY_VAR", value="hello world", type=ParameterType.STRING)
        assert param.to_env_line() == 'MY_VAR="hello world"'

    def test_name_must_start_with_slash(self):
        with pytest.raises(ValueError, match="must start with '/'"):
            SSMParameter(name="no-slash", value="v", type=ParameterType.STRING)

    def test_to_dict_contains_expected_keys(self):
        param = SSMParameter(name="/a/MY_VAR", value="val", type=ParameterType.STRING)
        d = param.to_dict()
        assert "name" in d
        assert "env_variable" in d
        assert "value" in d
        assert "type" in d

    def test_in_memory_encryption_disabled(self):
        from ssm_explorer.config import cfg
        cfg.security.in_memory_encryption = False
        param = SSMParameter(name="/a/MY_VAR", value="supersecret", type=ParameterType.STRING)
        assert param.value == "supersecret"
        assert param.__dict__.get("value") == "supersecret"

    def test_in_memory_encryption_enabled(self):
        from ssm_explorer.config import cfg
        cfg.security.in_memory_encryption = True
        try:
            param = SSMParameter(name="/a/MY_VAR", value="supersecret", type=ParameterType.STRING)
            assert param.value == "supersecret"
            assert param.__dict__.get("value") == "[ENCRYPTED_IN_MEMORY]"

            # Updating value
            param.value = "newsecret"
            assert param.value == "newsecret"
            assert param.__dict__.get("value") == "[ENCRYPTED_IN_MEMORY]"
        finally:
            cfg.security.in_memory_encryption = False


class TestSearchResult:
    def test_filter_by_path_case_insensitive(self, sample_search_result: SearchResult):
        filtered = sample_search_result.filter_by_path("/TEST/PATH/database")
        assert filtered.total_count == 1
        assert filtered.parameters[0].name == "/test/path/DATABASE_URL"

    def test_filter_by_path_no_match(self, sample_search_result: SearchResult):
        filtered = sample_search_result.filter_by_path("/nope")
        assert filtered.total_count == 0

    def test_filter_by_name_case_insensitive(self, sample_search_result: SearchResult):
        filtered = sample_search_result.filter_by_name("database")
        assert filtered.total_count == 1
        assert filtered.parameters[0].env_variable_name == "DATABASE_URL"

    def test_filter_by_name_no_match(self, sample_search_result: SearchResult):
        filtered = sample_search_result.filter_by_name("NONEXISTENT_KEY")
        assert filtered.total_count == 0

    def test_filter_by_value(self, sample_search_result: SearchResult):
        filtered = sample_search_result.filter_by_value("postgres")
        assert filtered.total_count == 1

    def test_filter_by_value_case_insensitive(self, sample_search_result: SearchResult):
        filtered = sample_search_result.filter_by_value("POSTGRES")
        assert filtered.total_count == 1

    def test_to_env_file_content_contains_header(self, sample_search_result: SearchResult):
        content = sample_search_result.to_env_file_content()
        assert "# Generated by ssm-explorer" in content
        assert "/test/path" in content

    def test_to_env_file_content_contains_variables(self, sample_search_result: SearchResult):
        content = sample_search_result.to_env_file_content()
        assert "DATABASE_URL=" in content
        assert "API_KEY=" in content

    def test_to_json_list_returns_list_of_dicts(self, sample_search_result: SearchResult):
        data = sample_search_result.to_json_list()
        assert isinstance(data, list)
        assert len(data) == 2
        assert all("env_variable" in d for d in data)

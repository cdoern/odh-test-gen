"""
Unit tests for scripts/jira_utils.py

Tests Jira REST API client with retry logic, error handling,
and label merging. Mocks HTTP layer to avoid actual API calls.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest
import requests

from scripts.jira_utils import (
    AttachmentFetchError,
    add_labels,
    api_call,
    api_call_with_retry,
    download_attachment,
    get_issue,
    make_request,
    require_env,
)


class TestRequireEnv:
    """Tests for require_env function."""

    def test_require_env_present(self):
        """Test that require_env returns value when set."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            assert require_env("TEST_VAR") == "test_value"

    def test_require_env_missing(self):
        """Test that require_env exits when variable is missing."""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(SystemExit):
            require_env("MISSING_VAR")

    def test_require_env_can_raise_for_library_callers(self):
        """Test that library callers can receive a typed configuration error."""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(AttachmentFetchError):
            require_env("JIRA_URL", exit_on_missing=False)

    def test_require_env_falls_back_to_alias(self):
        """Test that require_env uses alias when canonical name is unset."""
        with patch.dict(os.environ, {"JIRA_BASE_URL": "https://jira.example.com"}, clear=True):
            assert require_env("JIRA_URL") == "https://jira.example.com"

    def test_require_env_canonical_takes_precedence(self):
        """Test that canonical name is preferred over alias."""
        env = {"JIRA_URL": "https://canonical.com", "JIRA_BASE_URL": "https://alias.com"}
        with patch.dict(os.environ, env, clear=True):
            assert require_env("JIRA_URL") == "https://canonical.com"

    def test_require_env_all_aliases(self):
        """Test all three alias mappings."""
        aliases = {
            "JIRA_BASE_URL": "https://jira.example.com",
            "JIRA_EMAIL": "user@example.com",
            "JIRA_API_TOKEN": "token123",
        }
        with patch.dict(os.environ, aliases, clear=True):
            assert require_env("JIRA_URL") == "https://jira.example.com"
            assert require_env("JIRA_USER") == "user@example.com"
            assert require_env("JIRA_TOKEN") == "token123"


class TestLibraryConfiguration:
    """Tests for non-exiting Jira configuration lookup used by library callers."""

    @pytest.mark.parametrize("missing", ["JIRA_URL", "JIRA_USER", "JIRA_TOKEN"])
    @patch("scripts.jira_utils.requests.request")
    def test_make_request_missing_configuration_is_typed(self, mock_request, missing):
        env_vars = {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_USER": "test_user",
            "JIRA_TOKEN": "secret-token",
        }
        env_vars.pop(missing)

        with patch.dict(os.environ, env_vars, clear=True), pytest.raises(AttachmentFetchError):
            make_request("GET", "/rest/api/2/issue/TEST-123")

        mock_request.assert_not_called()

    @pytest.mark.parametrize("missing", ["JIRA_URL", "JIRA_USER", "JIRA_TOKEN"])
    @patch("scripts.jira_utils.requests.get")
    def test_download_attachment_missing_configuration_is_typed(self, mock_get, missing):
        env_vars = {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_USER": "test_user",
            "JIRA_TOKEN": "secret-token",
        }
        env_vars.pop(missing)

        with patch.dict(os.environ, env_vars, clear=True), pytest.raises(AttachmentFetchError):
            download_attachment("https://jira.example.com/secure/attachment/42/strategy.md")

        mock_get.assert_not_called()


class TestMakeRequest:
    """Tests for make_request function."""

    @patch("scripts.jira_utils.requests.request")
    def test_make_request_success(self, mock_request):
        """Test successful API request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        env_vars = {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_USER": "test_user",
            "JIRA_TOKEN": "test_token",
        }

        with patch.dict(os.environ, env_vars):
            response = make_request("GET", "/rest/api/2/issue/TEST-123")

        assert response == mock_response
        mock_request.assert_called_once()

    @patch("scripts.jira_utils.requests.request")
    def test_make_request_http_error(self, mock_request):
        """Test that HTTP errors are raised."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.HTTPError()
        mock_request.return_value = mock_response

        env_vars = {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_USER": "test_user",
            "JIRA_TOKEN": "test_token",
        }

        with patch.dict(os.environ, env_vars), pytest.raises(requests.HTTPError):
            make_request("GET", "/rest/api/2/issue/MISSING-123")


class TestApiCall:
    """Tests for api_call function."""

    @patch("scripts.jira_utils.make_request")
    def test_api_call_returns_json(self, mock_make_request):
        """Test that api_call returns JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'{"key": "TEST-123"}'
        mock_response.json.return_value = {"key": "TEST-123", "fields": {}}
        mock_make_request.return_value = mock_response

        result = api_call("/rest/api/2/issue/TEST-123")

        assert result == {"key": "TEST-123", "fields": {}}
        mock_make_request.assert_called_once_with("GET", "/rest/api/2/issue/TEST-123", None, None)

    @patch("scripts.jira_utils.make_request")
    def test_api_call_handles_204_no_content(self, mock_make_request):
        """Test that api_call handles 204 No Content responses."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.content = b""
        mock_make_request.return_value = mock_response

        result = api_call("/rest/api/2/issue/TEST-123", method="PUT")

        assert result is None

    @patch("scripts.jira_utils.make_request")
    def test_api_call_handles_empty_content(self, mock_make_request):
        """Test that api_call handles empty response content."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b""
        mock_make_request.return_value = mock_response

        result = api_call("/rest/api/2/issue/TEST-123")

        assert result is None


class TestApiCallWithRetry:
    """Tests for api_call_with_retry function."""

    @patch("scripts.jira_utils.api_call")
    def test_retry_success_first_attempt(self, mock_api_call):
        """Test successful call on first attempt."""
        mock_api_call.return_value = {"key": "TEST-123"}

        result = api_call_with_retry("/rest/api/2/issue/TEST-123")

        assert result == {"key": "TEST-123"}
        assert mock_api_call.call_count == 1

    @patch("scripts.jira_utils.api_call")
    @patch("scripts.jira_utils.time.sleep")
    def test_retry_success_after_failure(self, mock_sleep, mock_api_call):
        """Test successful call after transient 500 error."""
        mock_response = Mock()
        mock_response.status_code = 500

        # First call fails, second succeeds
        mock_api_call.side_effect = [requests.HTTPError(response=mock_response), {"key": "TEST-123"}]

        result = api_call_with_retry("/rest/api/2/issue/TEST-123", max_retries=3)

        assert result == {"key": "TEST-123"}
        assert mock_api_call.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("scripts.jira_utils.api_call")
    def test_no_retry_on_4xx_errors(self, mock_api_call):
        """Test that 4xx errors are not retried."""
        mock_response = Mock()
        mock_response.status_code = 404

        mock_api_call.side_effect = requests.HTTPError(response=mock_response)

        with pytest.raises(requests.HTTPError):
            api_call_with_retry("/rest/api/2/issue/MISSING-123", max_retries=3)

        # Should only try once for 4xx errors
        assert mock_api_call.call_count == 1

    @patch("scripts.jira_utils.api_call")
    @patch("builtins.print")
    def test_no_retry_on_auth_errors_with_message(self, mock_print, mock_api_call):
        """Test that auth errors (401, 403) are not retried and show helpful message."""
        for status_code in (401, 403):
            mock_print.reset_mock()
            mock_api_call.reset_mock()

            mock_response = Mock()
            mock_response.status_code = status_code
            mock_api_call.side_effect = requests.HTTPError(response=mock_response)

            with pytest.raises(requests.HTTPError):
                api_call_with_retry("/rest/api/2/issue/TEST-123", max_retries=3)

            # Should only try once for auth errors
            assert mock_api_call.call_count == 1

            # Should print helpful message to stderr
            stderr_calls = [call for call in mock_print.call_args_list if call.kwargs.get("file") == sys.stderr]
            assert stderr_calls
            error_msg = stderr_calls[0].args[0]
            assert "Authentication error" in error_msg or f"({status_code})" in error_msg
            assert "JIRA_" in error_msg  # Mentions env vars

    @patch("scripts.jira_utils.api_call")
    @patch("scripts.jira_utils.time.sleep")
    def test_retry_exhaustion(self, mock_sleep, mock_api_call):
        """Test that all retries are exhausted on persistent 500 error."""
        mock_response = Mock()
        mock_response.status_code = 500

        mock_api_call.side_effect = requests.HTTPError(response=mock_response)

        with pytest.raises(requests.HTTPError):
            api_call_with_retry("/rest/api/2/issue/TEST-123", max_retries=3)

        assert mock_api_call.call_count == 3
        assert mock_sleep.call_count == 2


class TestGetIssue:
    """Tests for get_issue function."""

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_get_issue_basic(self, mock_api_call):
        """Test basic issue fetch."""
        expected = {"key": "TEST-123", "fields": {"summary": "Test issue"}}
        mock_api_call.return_value = expected

        result = get_issue("TEST-123")

        assert result == expected
        mock_api_call.assert_called_once_with("/rest/api/2/issue/TEST-123", params={})

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_get_issue_with_fields(self, mock_api_call):
        """Test issue fetch with field filter."""
        expected = {"key": "TEST-123", "fields": {"summary": "Test"}}
        mock_api_call.return_value = expected

        result = get_issue("TEST-123", fields="summary,labels")

        assert result == expected
        mock_api_call.assert_called_once_with("/rest/api/2/issue/TEST-123", params={"fields": "summary,labels"})

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_get_issue_url_encodes_crafted_key(self, mock_api_call):
        mock_api_call.return_value = {}
        crafted_key = "PROJ-1/injected?x=y"

        get_issue(crafted_key)

        actual_endpoint = mock_api_call.call_args[0][0]
        assert actual_endpoint == "/rest/api/2/issue/PROJ-1%2Finjected%3Fx%3Dy"

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_get_issue_normal_key_is_unchanged(self, mock_api_call):
        # A well-formed key like "RHOAIENG-123" contains no special characters; URL-encoding
        # must leave it identical so the happy path is unaffected.
        mock_api_call.return_value = {}

        get_issue("RHOAIENG-123")

        actual_endpoint = mock_api_call.call_args[0][0]
        assert actual_endpoint == "/rest/api/2/issue/RHOAIENG-123"


class TestDownloadAttachment:
    """Tests authenticated reads of Jira attachment content."""

    @patch("scripts.jira_utils.requests.get")
    def test_downloads_content_url_with_configured_credentials(self, mock_get):
        response = Mock()
        response.text = "## Strategy\n"
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        env_vars = {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_USER": "test_user",
            "JIRA_TOKEN": "secret-token",
        }

        with patch.dict(os.environ, env_vars):
            result = download_attachment("https://jira.example.com/secure/attachment/42/strategy.md")

        assert result == "## Strategy\n"
        mock_get.assert_called_once()
        request = mock_get.call_args
        assert request.args[0] == "https://jira.example.com/secure/attachment/42/strategy.md"
        assert request.kwargs["auth"] == ("test_user", "secret-token")
        assert "secret-token" not in request.args[0]

    @patch("scripts.jira_utils.requests.get")
    def test_attachment_download_error_does_not_expose_token(self, mock_get):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("attachment unavailable")
        mock_get.return_value = response

        env_vars = {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_USER": "test_user",
            "JIRA_TOKEN": "secret-token",
        }

        with patch.dict(os.environ, env_vars), pytest.raises(AttachmentFetchError) as exc_info:
            download_attachment("https://jira.example.com/secure/attachment/42/strategy.md")

        assert "secret-token" not in str(exc_info.value)

    @patch("scripts.jira_utils.requests.get")
    def test_url_validation_and_transport_failures_share_one_typed_error(self, mock_get):
        env_vars = {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_USER": "test_user",
            "JIRA_TOKEN": "secret-token",
        }

        with patch.dict(os.environ, env_vars):
            with pytest.raises(AttachmentFetchError) as validation_error:
                download_attachment("https://evil.example.com/secure/attachment/42/strategy.md")

            mock_get.assert_not_called()
            mock_get.side_effect = requests.ConnectionError("attachment transport failed")

            with pytest.raises(AttachmentFetchError) as transport_error:
                download_attachment("https://jira.example.com/secure/attachment/42/strategy.md")

        assert type(validation_error.value) is type(transport_error.value)
        mock_get.assert_called_once()

    @pytest.mark.parametrize(
        "content_url",
        [
            "not-a-url",
            "/secure/attachment/42/strategy.md",
            "https://evil.example.com/secure/attachment/42/strategy.md",
            "https://jira.example.com:8443/secure/attachment/42/strategy.md",
            "http://jira.example.com/secure/attachment/42/strategy.md",
        ],
    )
    @patch("scripts.jira_utils.requests.get")
    def test_rejects_malformed_or_cross_origin_urls_before_sending_credentials(self, mock_get, content_url):
        env_vars = {
            "JIRA_URL": "https://jira.example.com",
            "JIRA_USER": "test_user",
            "JIRA_TOKEN": "secret-token",
        }

        with patch.dict(os.environ, env_vars), pytest.raises(AttachmentFetchError):
            download_attachment(content_url)

        mock_get.assert_not_called()

    @patch("scripts.jira_utils._jira_auth")
    @patch("scripts.jira_utils.requests.get")
    def test_rejects_same_origin_http_before_loading_credentials(self, mock_get, mock_auth):
        env_vars = {
            "JIRA_URL": "http://jira.example.com:8080/jira",
            "JIRA_USER": "test_user",
            "JIRA_TOKEN": "secret-token",
        }

        with patch.dict(os.environ, env_vars), pytest.raises(AttachmentFetchError):
            download_attachment("http://jira.example.com:8080/secure/attachment/42/strategy.md")

        mock_auth.assert_not_called()
        mock_get.assert_not_called()


class TestAddLabels:
    """Tests for add_labels function."""

    @patch("scripts.jira_utils.api_call_with_retry")
    @patch("scripts.jira_utils.get_issue")
    def test_add_labels_to_empty(self, mock_get_issue, mock_api_call):
        """Test adding labels to issue with no existing labels."""
        mock_get_issue.return_value = {"key": "TEST-123", "fields": {"labels": []}}
        mock_api_call.return_value = None  # 204 No Content

        result = add_labels("TEST-123", ["new-label"])

        # Should return None (void function)
        assert result is None

        # Verify the update call
        mock_api_call.assert_called_once_with(
            "/rest/api/2/issue/TEST-123", method="PUT", json_data={"fields": {"labels": ["new-label"]}}
        )

    @patch("scripts.jira_utils.api_call_with_retry")
    @patch("scripts.jira_utils.get_issue")
    def test_add_labels_merge_existing(self, mock_get_issue, mock_api_call):
        """Test that new labels are merged with existing labels."""
        mock_get_issue.return_value = {"key": "TEST-123", "fields": {"labels": ["existing-label"]}}
        mock_api_call.return_value = None  # 204 No Content

        add_labels("TEST-123", ["new-label"])

        # Should contain both labels
        call_args = mock_api_call.call_args
        labels = call_args[1]["json_data"]["fields"]["labels"]
        assert set(labels) == {"existing-label", "new-label"}

    @patch("scripts.jira_utils.api_call_with_retry")
    @patch("scripts.jira_utils.get_issue")
    def test_add_labels_no_duplicates(self, mock_get_issue, mock_api_call):
        """Test that duplicate labels are not added."""
        mock_get_issue.return_value = {"key": "TEST-123", "fields": {"labels": ["existing-label"]}}
        mock_api_call.return_value = None  # 204 No Content

        add_labels("TEST-123", ["existing-label", "new-label"])

        # Should deduplicate
        call_args = mock_api_call.call_args
        labels = call_args[1]["json_data"]["fields"]["labels"]
        assert set(labels) == {"existing-label", "new-label"}
        assert len(labels) == 2

    @patch("scripts.jira_utils.api_call_with_retry")
    @patch("scripts.jira_utils.get_issue")
    def test_add_labels_preserves_order(self, mock_get_issue, mock_api_call):
        """Test that label order is deterministic (existing first, new appended)."""
        mock_get_issue.return_value = {"key": "TEST-123", "fields": {"labels": ["label-a", "label-b", "label-c"]}}
        mock_api_call.return_value = None  # 204 No Content

        add_labels("TEST-123", ["label-d", "label-e"])

        # Should preserve existing order and append new labels
        call_args = mock_api_call.call_args
        labels = call_args[1]["json_data"]["fields"]["labels"]
        assert labels == ["label-a", "label-b", "label-c", "label-d", "label-e"]

    @patch("scripts.jira_utils.api_call_with_retry")
    @patch("scripts.jira_utils.get_issue")
    def test_add_labels_skips_api_call_when_no_change(self, mock_get_issue, mock_api_call):
        """Test that no API call is made when all labels already exist."""
        mock_get_issue.return_value = {"key": "TEST-123", "fields": {"labels": ["existing-label", "another-label"]}}

        add_labels("TEST-123", ["existing-label"])

        # Should NOT call the update API (all labels already present)
        mock_api_call.assert_not_called()

    @patch("scripts.jira_utils.api_call_with_retry")
    @patch("scripts.jira_utils.get_issue")
    def test_add_labels_deterministic_order(self, mock_get_issue, mock_api_call):
        """Test that label order is deterministic (no set() randomness)."""
        mock_get_issue.return_value = {"key": "TEST-123", "fields": {"labels": ["z", "a", "m"]}}
        mock_api_call.return_value = None

        # Add labels
        add_labels("TEST-123", ["b", "y"])

        # Should preserve existing order and append new labels in given order
        call_args = mock_api_call.call_args
        labels = call_args[1]["json_data"]["fields"]["labels"]

        # Verify exact order (not set-based which would be random)
        assert labels == ["z", "a", "m", "b", "y"]

    @patch("scripts.jira_utils.api_call_with_retry")
    @patch("scripts.jira_utils.get_issue")
    def test_add_labels_removes_stale_before_adding_replacement(self, mock_get_issue, mock_api_call):
        """A verdict change (e.g. Ready -> Revise) must replace the old rubric label, not
        accumulate alongside it — regression test for the CodeRabbit finding on PR #46.
        """
        mock_get_issue.return_value = {
            "key": "TEST-123",
            "fields": {"labels": ["test-plan-rubric-pass", "unrelated-label"]},
        }
        mock_api_call.return_value = None  # 204 No Content

        add_labels("TEST-123", ["test-plan-rubric-revise"], remove=["test-plan-rubric-pass"])

        call_args = mock_api_call.call_args
        labels = call_args[1]["json_data"]["fields"]["labels"]
        assert labels == ["unrelated-label", "test-plan-rubric-revise"]

    @patch("scripts.jira_utils.api_call_with_retry")
    @patch("scripts.jira_utils.get_issue")
    def test_add_labels_remove_is_noop_when_label_not_present(self, mock_get_issue, mock_api_call):
        mock_get_issue.return_value = {"key": "TEST-123", "fields": {"labels": ["unrelated-label"]}}
        mock_api_call.return_value = None

        add_labels("TEST-123", ["test-plan-rubric-pass"], remove=["test-plan-rubric-revise"])

        call_args = mock_api_call.call_args
        labels = call_args[1]["json_data"]["fields"]["labels"]
        assert labels == ["unrelated-label", "test-plan-rubric-pass"]

    @patch("scripts.jira_utils.api_call_with_retry")
    @patch("scripts.jira_utils.get_issue")
    def test_add_labels_url_encodes_crafted_key(self, mock_get_issue, mock_api_call):
        mock_get_issue.return_value = {"key": "PROJ-1/injected?x=y", "fields": {"labels": []}}
        mock_api_call.return_value = None  # 204 No Content
        crafted_key = "PROJ-1/injected?x=y"

        add_labels(crafted_key, ["new-label"])

        actual_endpoint = mock_api_call.call_args[0][0]
        assert actual_endpoint == "/rest/api/2/issue/PROJ-1%2Finjected%3Fx%3Dy"

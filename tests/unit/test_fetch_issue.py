"""
Unit tests for scripts/fetch_issue.py

Tests Jira issue markdown formatting logic.
"""

import json
import sys
from unittest.mock import patch

import pytest
import requests

from scripts.fetch_issue import main
from scripts.jira_utils import AttachmentFetchError
from scripts.strategy_source import (
    OVERFLOW_MARKER,
    format_issue_as_markdown,
    parse_components,
    select_strategy_attachment,
)
from scripts.utils.strat_utils import workflow_inputs


ISSUE_KEY = "TEST-999"
OVERFLOW_DESCRIPTION = (
    f"The full strategy {OVERFLOW_MARKER} and is stored as an attachment: "
    f"{{{{{ISSUE_KEY}-strategy.md}}}}. The TL;DR is shown below for quick reference."
)


def _attachment(
    filename,
    *,
    created="2026-09-01T12:00:00.000+0000",
    attachment_id="1",
    content="https://jira.example/1",
):
    return {
        "filename": filename,
        "created": created,
        "id": attachment_id,
        "content": content,
    }


def _issue(description, attachments=None):
    return {
        "key": ISSUE_KEY,
        "fields": {
            "summary": "Resolve strategy attachment",
            "description": description,
            "issuetype": {"name": "Story"},
            "status": {"name": "Open"},
            "labels": [],
            "components": [],
            "attachment": attachments or [],
        },
    }


FULL_MARKDOWN_STRATEGY = """## Strategy

### Acceptance Criteria

1. *Attachment wins*: Given an overflow description When the strategy is fetched Then the newest attachment is parsed

### Non-Functional Requirements

* *Performance*: The strategy fetch completes within the request timeout

### Out-of-Scope

* *Legacy UI*: Reworking the unrelated legacy UI is excluded
"""

SENSITIVE_HTTP_ERROR = "500 Server Error: https://issues.example.com/rest/api/2/issue/TEST-999?token=abc123"


class TestFormatIssueAsMarkdown:
    """Tests for format_issue_as_markdown function."""

    def test_basic_issue_formatting(self):
        """Test formatting a basic issue."""
        issue_data = {
            "key": "TEST-123",
            "fields": {
                "summary": "Test issue summary",
                "description": "Test description",
                "issuetype": {"name": "Story"},
                "status": {"name": "In Progress"},
                "labels": [],
                "components": [],
            },
        }

        result = format_issue_as_markdown(issue_data)

        assert "# TEST-123: Test issue summary" in result
        assert "- **Type**: Story" in result
        assert "- **Status**: In Progress" in result
        assert "## Description" in result
        assert "Test description" in result

    def test_issue_with_labels(self):
        """Test formatting issue with labels."""
        issue_data = {
            "key": "TEST-123",
            "fields": {
                "summary": "Test",
                "description": "Desc",
                "issuetype": {"name": "Task"},
                "status": {"name": "Done"},
                "labels": ["bug", "frontend"],
                "components": [],
            },
        }

        result = format_issue_as_markdown(issue_data)

        assert "- **Labels**: bug, frontend" in result

    def test_issue_with_components(self):
        """Test formatting issue with components."""
        issue_data = {
            "key": "TEST-123",
            "fields": {
                "summary": "Test",
                "description": "Desc",
                "issuetype": {"name": "Bug"},
                "status": {"name": "Open"},
                "labels": [],
                "components": [{"name": "Backend"}, {"name": "API"}],
            },
        }

        result = format_issue_as_markdown(issue_data)

        assert "- **Components**: Backend, API" in result

    def test_issue_with_missing_fields(self):
        """Test formatting issue with missing optional fields."""
        issue_data = {"key": "TEST-123", "fields": {}}

        result = format_issue_as_markdown(issue_data)

        assert "# TEST-123: No summary" in result
        assert "No description provided" in result
        assert "- **Type**: Unknown" in result
        assert "- **Status**: Unknown" in result

    def test_explicit_null_description_uses_fallback(self):
        """Jira's explicit null description has the same fallback as a missing description."""
        result = format_issue_as_markdown(_issue(None))

        assert "No description provided" in result


class TestStrategyAttachmentResolution:
    """Regression coverage for the append-only strategy attachment producer contract."""

    def test_selects_exact_strategy_filename_and_ignores_similar_orphan_files(self):
        attachments = [
            _attachment(f"{ISSUE_KEY}-strategy-review.md", content="https://jira.example/review"),
            _attachment("OTHER-999-strategy.md", content="https://jira.example/other"),
            _attachment(f"{ISSUE_KEY}-strategy.md.bak", content="https://jira.example/bak"),
            _attachment(f"{ISSUE_KEY}-strategy.md", content="https://jira.example/exact"),
        ]

        assert select_strategy_attachment(ISSUE_KEY, attachments)["content"] == "https://jira.example/exact"

    @pytest.mark.parametrize(
        "attachments,expected_url",
        [
            (
                [
                    _attachment(f"{ISSUE_KEY}-strategy.md", attachment_id="8", content="https://jira.example/8"),
                    _attachment(f"{ISSUE_KEY}-strategy.md", attachment_id="7", content="https://jira.example/7"),
                ],
                "https://jira.example/8",
            ),
            (
                [
                    _attachment(
                        f"{ISSUE_KEY}-strategy.md", attachment_id="alpha", content="https://jira.example/alpha"
                    ),
                    _attachment(f"{ISSUE_KEY}-strategy.md", attachment_id="beta", content="https://jira.example/beta"),
                ],
                "https://jira.example/beta",
            ),
            (
                [
                    _attachment(
                        f"{ISSUE_KEY}-strategy.md", attachment_id="nonnumeric", content="https://jira.example/z"
                    ),
                    _attachment(f"{ISSUE_KEY}-strategy.md", attachment_id="12", content="https://jira.example/12"),
                ],
                "https://jira.example/12",
            ),
            (
                [
                    _attachment(f"{ISSUE_KEY}-strategy.md", attachment_id="same", content="https://jira.example/a"),
                    _attachment(f"{ISSUE_KEY}-strategy.md", attachment_id="same", content="https://jira.example/b"),
                ],
                "https://jira.example/b",
            ),
        ],
    )
    def test_newest_selection_is_deterministic_for_duplicate_attachments(self, attachments, expected_url):
        attachments[0]["created"] = attachments[1]["created"] = "2026-09-01T12:00:00.000+0000"

        assert select_strategy_attachment(ISSUE_KEY, list(reversed(attachments)))["content"] == expected_url

    def test_newer_created_attachment_wins_regardless_of_jira_list_order(self):
        older = _attachment(
            f"{ISSUE_KEY}-strategy.md",
            created="2026-09-01T12:00:00.000+0000",
            attachment_id="99",
            content="https://jira.example/older",
        )
        newer = _attachment(
            f"{ISSUE_KEY}-strategy.md",
            created="2026-09-02T12:00:00.000+0000",
            attachment_id="1",
            content="https://jira.example/newer",
        )

        assert select_strategy_attachment(ISSUE_KEY, [newer, older])["content"] == "https://jira.example/newer"

    @patch("scripts.strategy_source.download_attachment", return_value=FULL_MARKDOWN_STRATEGY)
    def test_overflow_marker_resolves_newest_attachment_and_normalizes_markdown_headings(self, mock_download):
        older = _attachment(
            f"{ISSUE_KEY}-strategy.md",
            created="2026-09-01T12:00:00.000+0000",
            content="https://jira.example/older",
        )
        newer = _attachment(
            f"{ISSUE_KEY}-strategy.md",
            created="2026-09-02T12:00:00.000+0000",
            content="https://jira.example/newer",
        )

        result = format_issue_as_markdown(_issue(OVERFLOW_DESCRIPTION, [newer, older]))

        mock_download.assert_called_once_with("https://jira.example/newer")
        assert "h2. Strategy" in result
        assert "h3. Acceptance Criteria" in result
        assert "### Acceptance Criteria" not in result

    @patch("scripts.strategy_source.download_attachment", return_value=FULL_MARKDOWN_STRATEGY)
    def test_matching_attachment_is_orphan_when_overflow_marker_is_absent(self, mock_download):
        description = "h3. Acceptance Criteria\n\n# *Description wins*: The in-limit description remains authoritative."

        result = format_issue_as_markdown(
            _issue(description, [_attachment(f"{ISSUE_KEY}-strategy.md", content="https://jira.example/orphan")])
        )

        mock_download.assert_not_called()
        assert description in result
        assert "Attachment wins" not in result

    @patch("scripts.strategy_source.download_attachment", return_value=FULL_MARKDOWN_STRATEGY)
    def test_resolved_attachment_reaches_workflow_inputs_successfully(self, mock_download):
        older = _attachment(
            f"{ISSUE_KEY}-strategy.md",
            created="2026-09-01T12:00:00.000+0000",
            content="https://jira.example/older",
        )
        newer = _attachment(
            f"{ISSUE_KEY}-strategy.md",
            created="2026-09-02T12:00:00.000+0000",
            content="https://jira.example/newer",
        )

        result = workflow_inputs(format_issue_as_markdown(_issue(OVERFLOW_DESCRIPTION, [older, newer])))

        assert result["status"] == "ok"
        assert result["ac_json"]["count"] == 1
        assert "Attachment wins" in result["ac_json"]["acceptance_criteria"][0]["text"]
        assert result["nfr_json"]["requirements"][0]["category"] == "Performance"
        assert result["oos_json"]["items"][0]["title"] == "Legacy UI"
        mock_download.assert_called_once_with("https://jira.example/newer")

    @patch(
        "scripts.strategy_source.download_attachment",
        return_value="## Strategy\n\n### Risks\n\nThe attachment has no acceptance criteria.\n",
    )
    def test_resolved_body_without_acceptance_criteria_preserves_stop_behavior(self, mock_download):
        result = workflow_inputs(
            format_issue_as_markdown(
                _issue(
                    OVERFLOW_DESCRIPTION,
                    [_attachment(f"{ISSUE_KEY}-strategy.md", content="https://jira.example/no-ac")],
                )
            )
        )

        assert result["status"] == "no_acceptance_criteria"
        assert result["ac_json"]["found"] is False
        mock_download.assert_called_once_with("https://jira.example/no-ac")

    @pytest.mark.parametrize("fence", ["```", "~~~"])
    @patch("scripts.strategy_source.download_attachment")
    def test_heading_normalization_preserves_fenced_code_blocks(self, mock_download, fence):
        mock_download.return_value = (
            f"## Strategy\n\n{fence}markdown\n## Literal heading\n### Literal subheading\n{fence}\n\n"
            "### Acceptance Criteria\n\n1. *AC*: Given a strategy Then the body is preserved\n"
        )

        result = format_issue_as_markdown(_issue(OVERFLOW_DESCRIPTION, [_attachment(f"{ISSUE_KEY}-strategy.md")]))

        assert "h2. Strategy" in result
        assert "h3. Acceptance Criteria" in result
        assert f"{fence}markdown\n## Literal heading\n### Literal subheading\n{fence}" in result
        assert f"{fence}markdown\nh2. Literal heading\nh3. Literal subheading\n{fence}" not in result


class TestFetchIssueCLI:
    """Tests for the direct fetch_issue CLI boundary."""

    @patch("scripts.fetch_issue.get_issue")
    def test_fetches_complete_issue_without_field_filter(self, mock_get_issue):
        mock_get_issue.return_value = _issue("Description")

        with patch.object(sys, "argv", ["fetch_issue.py", ISSUE_KEY]):
            main()

        mock_get_issue.assert_called_once_with(ISSUE_KEY, fields=None)

    @patch("scripts.strategy_source.download_attachment")
    @patch("scripts.fetch_issue.get_issue")
    def test_attachment_failure_does_not_print_raw_request_details(self, mock_get_issue, mock_download, capsys):
        mock_get_issue.return_value = _issue(
            OVERFLOW_DESCRIPTION, [_attachment(f"{ISSUE_KEY}-strategy.md", content="https://issues.example.com/42")]
        )
        mock_download.side_effect = AttachmentFetchError(SENSITIVE_HTTP_ERROR)

        with patch.object(sys, "argv", ["fetch_issue.py", ISSUE_KEY]), pytest.raises(SystemExit) as exc_info:
            main()

        captured = capsys.readouterr()
        assert exc_info.value.code == 1
        assert json.loads(captured.out) == {"status": "failed", "error": "jira_fetch_failed"}
        assert "issues.example.com" not in captured.out + captured.err
        assert "token=abc123" not in captured.out + captured.err

    @patch("scripts.fetch_issue.get_issue", side_effect=requests.HTTPError(SENSITIVE_HTTP_ERROR))
    def test_jira_request_failure_returns_sanitized_structured_error(self, mock_get_issue, capsys):
        with patch.object(sys, "argv", ["fetch_issue.py", ISSUE_KEY]), pytest.raises(SystemExit) as exc_info:
            main()

        captured = capsys.readouterr()
        assert exc_info.value.code == 1
        assert json.loads(captured.out) == {"status": "failed", "error": "jira_fetch_failed"}
        assert "issues.example.com" not in captured.out + captured.err
        assert "token=abc123" not in captured.out + captured.err
        mock_get_issue.assert_called_once_with(ISSUE_KEY, fields=None)

    @patch("scripts.fetch_issue.get_issue")
    def test_output_write_failure_returns_sanitized_structured_error(self, mock_get_issue, capsys):
        mock_get_issue.return_value = _issue("Description")

        with (
            patch.object(sys, "argv", ["fetch_issue.py", ISSUE_KEY, "--output", "strategy.md"]),
            patch("builtins.open", side_effect=OSError("disk full")),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        captured = capsys.readouterr()
        assert exc_info.value.code == 1
        assert json.loads(captured.out) == {"status": "failed", "error": "output_write_failed"}
        assert "disk full" not in captured.out + captured.err

    @patch("scripts.fetch_issue.format_issue_as_markdown", side_effect=RuntimeError("formatter bug"))
    @patch("scripts.fetch_issue.get_issue")
    def test_programming_failure_is_not_reported_as_jira_fetch_failure(self, mock_get_issue, mock_format):
        mock_get_issue.return_value = _issue("Description")

        with (
            patch.object(sys, "argv", ["fetch_issue.py", ISSUE_KEY]),
            pytest.raises(RuntimeError, match="formatter bug"),
        ):
            main()

        mock_format.assert_called_once()


class TestParseComponents:
    """Tests for parse_components — the inverse of format_issue_as_markdown's Components bullet,
    used by test-plan-create to extract components from a saved strategy snapshot without an LLM
    reading and eyeballing the file.
    """

    @pytest.mark.parametrize(
        "components,expected",
        [
            ([{"name": "AI Hub"}, {"name": "Model Serving"}], ["AI Hub", "Model Serving"]),
            ([{"name": "AI Hub"}], ["AI Hub"]),
            ([], []),
        ],
    )
    def test_round_trips_with_format_issue_as_markdown(self, components, expected):
        issue_data = {"key": "TEST-123", "fields": {"components": components}}

        markdown = format_issue_as_markdown(issue_data)

        assert parse_components(markdown) == expected

    def test_ignores_components_bullet_in_description(self):
        issue_data = {
            "key": "TEST-123",
            "fields": {
                "components": [],
                "description": "Some description text\n- **Components**: Fake, Injected",
            },
        }

        markdown = format_issue_as_markdown(issue_data)

        assert parse_components(markdown) == []

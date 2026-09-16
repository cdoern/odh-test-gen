"""Unit tests for scripts/resolve_strategy.py — snapshot-primary strategy resolution shared by
test-plan-review and test-plan-score.

Mocks at the same boundary as test_jira_utils.py (api_call_with_retry) so get_issue and
format_issue_as_markdown run for real — resolve_strategy is exercised through its actual
dependencies, not a hand-built stand-in for what they return.
"""

import json
import os
import sys
from unittest.mock import patch

import pytest
import requests

from scripts.resolve_strategy import main, resolve_strategy
from scripts.strategy_source import OVERFLOW_MARKER

# Stands in for what a real Jira error can contain — request URL, query params, server body —
# none of which should ever reach stdout/logs.
SENSITIVE_HTTP_ERROR = "500 Server Error: https://issues.example.com/rest/api/2/issue/RHAISTRAT-1746?token=abc123"
JIRA_ENV = {
    "JIRA_URL": "https://issues.example.com",
    "JIRA_USER": "test_user",
    "JIRA_TOKEN": "secret-token",
}


class TestResolveStrategy:
    @patch("scripts.jira_utils.api_call_with_retry")
    def test_snapshot_hit_returns_its_path_without_fetching(self, mock_api_call, tmp_path):
        snapshot = tmp_path / ".source-strategy.md"
        snapshot.write_text("# Cached strategy\n")

        result = resolve_strategy(str(tmp_path), "RHAISTRAT-1746")

        assert result == {"status": "ok", "source": "snapshot", "strategy_file": str(snapshot)}
        mock_api_call.assert_not_called()

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_refetch_on_missing_snapshot_saves_it(self, mock_api_call, tmp_path):
        mock_api_call.return_value = {
            "key": "RHAISTRAT-1746",
            "fields": {"summary": "Vector store registration"},
        }

        result = resolve_strategy(str(tmp_path), "RHAISTRAT-1746")

        snapshot = tmp_path / ".source-strategy.md"
        assert result == {"status": "ok", "source": "refetch", "strategy_file": str(snapshot)}
        assert "Vector store registration" in snapshot.read_text()
        mock_api_call.assert_called_once_with("/rest/api/2/issue/RHAISTRAT-1746", params={})

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_hard_fail_when_no_snapshot_and_fetch_fails(self, mock_api_call, tmp_path):
        error = requests.HTTPError(SENSITIVE_HTTP_ERROR)
        mock_api_call.side_effect = error

        with pytest.raises(requests.HTTPError) as exc_info:
            resolve_strategy(str(tmp_path), "RHAISTRAT-1746")

        assert exc_info.value is error
        assert not (tmp_path / ".source-strategy.md").exists()

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_creates_feature_dir_if_missing_before_writing_snapshot(self, mock_api_call, tmp_path):
        mock_api_call.return_value = {
            "key": "RHAISTRAT-1746",
            "fields": {"summary": "Vector store registration"},
        }
        feature_dir = tmp_path / "not_yet_created"

        result = resolve_strategy(str(feature_dir), "RHAISTRAT-1746")

        snapshot = feature_dir / ".source-strategy.md"
        assert result == {"status": "ok", "source": "refetch", "strategy_file": str(snapshot)}
        assert "Vector store registration" in snapshot.read_text()

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_snapshot_write_failure_raises_oserror(self, mock_api_call, tmp_path):
        mock_api_call.return_value = {
            "key": "RHAISTRAT-1746",
            "fields": {"summary": "Vector store registration"},
        }
        # A plain file sitting where the feature directory should be: mkdir(exist_ok=True) still
        # raises for a non-directory occupant, exercising the write-failure path deterministically.
        blocked_feature_dir = tmp_path / "blocked"
        blocked_feature_dir.write_text("not a directory")

        with pytest.raises(OSError):
            resolve_strategy(str(blocked_feature_dir), "RHAISTRAT-1746")


class TestResolveStrategyCLI:
    def test_missing_jira_configuration_maps_to_fetch_failure(self, tmp_path, capsys):
        old_argv = sys.argv
        try:
            sys.argv = ["resolve_strategy.py", str(tmp_path), "RHAISTRAT-1746"]
            with patch.dict(os.environ, {}, clear=True), pytest.raises(SystemExit) as exc_info:
                main()
        finally:
            sys.argv = old_argv

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"status": "failed", "error": "jira_fetch_failed"}
        assert "JIRA_" not in captured.out
        assert "JIRA_" not in captured.err

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_ok_path_prints_status_ok_and_exits_zero(self, mock_api_call, tmp_path, capsys):
        mock_api_call.return_value = {
            "key": "RHAISTRAT-1746",
            "fields": {"summary": "Vector store registration"},
        }

        old_argv = sys.argv
        try:
            sys.argv = ["resolve_strategy.py", str(tmp_path), "RHAISTRAT-1746"]
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 0
            else:
                raise AssertionError("main() must exit")
        finally:
            sys.argv = old_argv

        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "ok"
        assert output["source"] == "refetch"

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_fetch_failure_exits_one_with_stable_error_code(self, mock_api_call, tmp_path, capsys):
        mock_api_call.side_effect = requests.HTTPError(SENSITIVE_HTTP_ERROR)

        old_argv = sys.argv
        try:
            sys.argv = ["resolve_strategy.py", str(tmp_path), "RHAISTRAT-1746"]
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 1
            else:
                raise AssertionError("main() must exit with code 1")
        finally:
            sys.argv = old_argv

        raw_output = capsys.readouterr().out
        output = json.loads(raw_output)
        assert output == {"status": "failed", "error": "jira_fetch_failed"}
        assert "issues.example.com" not in raw_output
        assert "token=abc123" not in raw_output

    @pytest.mark.parametrize(
        ("content_url", "transport_error"),
        [
            ("https://evil.example.com/secure/attachment/42/strategy.md", None),
            (
                "https://issues.example.com/secure/attachment/42/strategy.md",
                requests.ConnectionError(SENSITIVE_HTTP_ERROR),
            ),
        ],
    )
    def test_attachment_url_and_transport_failures_map_to_stable_error_code(
        self, content_url, transport_error, tmp_path, capsys
    ):
        issue_data = {
            "key": "RHAISTRAT-1746",
            "fields": {
                "summary": "Vector store registration",
                "description": f"The full strategy {OVERFLOW_MARKER}.",
                "attachment": [
                    {
                        "filename": "RHAISTRAT-1746-strategy.md",
                        "created": "2026-09-01T12:00:00.000+0000",
                        "id": "42",
                        "content": content_url,
                    }
                ],
            },
        }

        with (
            patch("scripts.jira_utils.api_call_with_retry", return_value=issue_data) as mock_api_call,
            patch("scripts.jira_utils.requests.get") as mock_get,
            patch.dict(os.environ, JIRA_ENV),
            patch.object(sys, "argv", ["resolve_strategy.py", str(tmp_path), "RHAISTRAT-1746"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_get.side_effect = transport_error
            main()

        captured = capsys.readouterr()
        assert exc_info.value.code == 1
        assert json.loads(captured.out) == {"status": "failed", "error": "jira_fetch_failed"}
        assert "issues.example.com" not in captured.out
        assert "issues.example.com" not in captured.err
        mock_api_call.assert_called_once_with("/rest/api/2/issue/RHAISTRAT-1746", params={})
        if transport_error is None:
            mock_get.assert_not_called()
        else:
            mock_get.assert_called_once()

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_snapshot_write_failure_exits_one_with_stable_error_code(self, mock_api_call, tmp_path, capsys):
        mock_api_call.return_value = {
            "key": "RHAISTRAT-1746",
            "fields": {"summary": "Vector store registration"},
        }
        blocked_feature_dir = tmp_path / "blocked"
        blocked_feature_dir.write_text("not a directory")

        old_argv = sys.argv
        try:
            sys.argv = ["resolve_strategy.py", str(blocked_feature_dir), "RHAISTRAT-1746"]
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 1
            else:
                raise AssertionError("main() must exit with code 1")
        finally:
            sys.argv = old_argv

        assert json.loads(capsys.readouterr().out) == {"status": "failed", "error": "snapshot_write_failed"}


class TestResolveStrategySymlinkRejection:
    """Verify that resolve_strategy's is_symlink() guard rejects a pre-existing symlink at the
    snapshot path before any Jira fetch or write — both a regular-file symlink and a dangling
    symlink must raise OSError, mapped to snapshot_write_failed at the CLI level.
    (write_snapshot_nofollow's own O_NOFOLLOW backstop is covered in tests/unit/test_snapshot_io.py.)
    """

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_refetch_rejects_symlink_to_regular_file(self, mock_api_call, tmp_path):
        victim = tmp_path / "victim.md"
        victim.write_text("must not be overwritten")
        (tmp_path / ".source-strategy.md").symlink_to(victim)

        with pytest.raises(OSError, match="snapshot path is a symlink"):
            resolve_strategy(str(tmp_path), "RHAISTRAT-1746")

        assert victim.read_text() == "must not be overwritten"
        mock_api_call.assert_not_called()

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_refetch_rejects_dangling_symlink(self, mock_api_call, tmp_path):
        (tmp_path / ".source-strategy.md").symlink_to(tmp_path / "nonexistent.md")

        with pytest.raises(OSError, match="snapshot path is a symlink"):
            resolve_strategy(str(tmp_path), "RHAISTRAT-1746")

        assert not (tmp_path / "nonexistent.md").exists()
        mock_api_call.assert_not_called()

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_refetch_symlink_cli_exits_one_with_snapshot_write_failed(self, mock_api_call, tmp_path, capsys):
        mock_api_call.return_value = {
            "key": "RHAISTRAT-1746",
            "fields": {"summary": "Vector store registration"},
        }
        victim = tmp_path / "victim.md"
        victim.write_text("must not be overwritten")
        (tmp_path / ".source-strategy.md").symlink_to(victim)

        old_argv = sys.argv
        try:
            sys.argv = ["resolve_strategy.py", str(tmp_path), "RHAISTRAT-1746"]
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 1
            else:
                raise AssertionError("main() must exit with code 1")
        finally:
            sys.argv = old_argv

        assert json.loads(capsys.readouterr().out) == {"status": "failed", "error": "snapshot_write_failed"}
        assert victim.read_text() == "must not be overwritten"

    @patch("scripts.jira_utils.api_call_with_retry")
    def test_refetch_dangling_symlink_cli_exits_one_with_snapshot_write_failed(self, mock_api_call, tmp_path, capsys):
        mock_api_call.return_value = {
            "key": "RHAISTRAT-1746",
            "fields": {"summary": "Vector store registration"},
        }
        (tmp_path / ".source-strategy.md").symlink_to(tmp_path / "nonexistent.md")

        old_argv = sys.argv
        try:
            sys.argv = ["resolve_strategy.py", str(tmp_path), "RHAISTRAT-1746"]
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 1
            else:
                raise AssertionError("main() must exit with code 1")
        finally:
            sys.argv = old_argv

        assert json.loads(capsys.readouterr().out) == {"status": "failed", "error": "snapshot_write_failed"}

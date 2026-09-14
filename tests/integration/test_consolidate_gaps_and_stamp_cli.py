"""
Integration tests for scripts/consolidate_gaps_and_stamp.py CLI.

This script wraps consolidate_gaps() + write_frontmatter_with_body() into the single
call test-plan-create's Step 3.5 needs: consolidate raw analyzer gap output, write
TestPlanGaps.md (body + stamped frontmatter) in one shot, delete the staged temp
source files, and print {"gap_count": int, "status": str, "next": str} to stdout.

Pure gap-consolidation logic (dedup, grouping, status derivation) is already covered by
tests/unit/test_consolidate_gaps.py — this file covers frontmatter stamping, temp-file
cleanup, the gaps-menu next-action gate, and failing before any output is written.
"""

import json
import os
import subprocess

import pytest

from scripts.utils.frontmatter_utils import read_frontmatter
from tests.constants import REPO_ROOT
from tests.consts.gaps_constants import (
    GAPS_ENDPOINTS_DUPLICATE,
    GAPS_INFRA_SINGLETON,
    GAPS_INFRA_ACTIONABILITY_ADVISORY_AND_BLOCKING,
    GAPS_INFRA_ACTIONABILITY_ADVISORY_ONLY,
    GAPS_NEXT_PROCEED,
    GAPS_NEXT_PROMPT_USER,
    GAPS_RISKS_DUPLICATE,
)
from tests.consts.validation_constants import ACTIONABILITY_ADVISORY_AND_BLOCKING_RESULT, ACTIONABILITY_ADVISORY_RESULT

LAST_UPDATED = "1999-12-31"


def _run_cli(*extra_args, env_overrides=None):
    env = os.environ.copy()
    env.pop("CI", None)
    env.pop("CLAUDE_NON_INTERACTIVE", None)
    if env_overrides:
        env.update(env_overrides)
    cmd = [
        "uv",
        "run",
        "python",
        str(REPO_ROOT / "scripts" / "consolidate_gaps_and_stamp.py"),
        "--last-updated",
        LAST_UPDATED,
        *extra_args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=REPO_ROOT, env=env)


@pytest.fixture
def feature_dir(tmp_path):
    d = tmp_path / "TestFeature"
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestConsolidateGapsAndStampCLI:
    def test_advisory_actionability_gaps_are_written_without_source_document_prompt(self, feature_dir):
        staging = feature_dir / ".analysis-infra.md"
        staging.write_text("## Gaps\n\nNo gaps identified.\n")
        out_file = feature_dir / "TestPlanGaps.md"

        result = _run_cli(
            "--feature-name",
            "Test Feature",
            "--source-key",
            "RHAISTRAT-400",
            "--source",
            f"infra={staging}",
            "--actionability-result",
            json.dumps(ACTIONABILITY_ADVISORY_RESULT),
            "--out",
            str(out_file),
        )

        assert result.returncode == 0, result.stderr
        stdout_data = json.loads(result.stdout)
        assert stdout_data["gap_count"] == 0
        assert stdout_data["next"] == GAPS_NEXT_PROCEED

        _, body = read_frontmatter(out_file)
        for gap in ACTIONABILITY_ADVISORY_RESULT["advisory_gaps"]:
            assert gap in body

    @pytest.mark.parametrize(
        "source_text, actionability_result, expected_gap_count, expected_next, blocking_group",
        (
            pytest.param(
                GAPS_INFRA_ACTIONABILITY_ADVISORY_ONLY,
                ACTIONABILITY_ADVISORY_RESULT,
                0,
                GAPS_NEXT_PROCEED,
                None,
                id="advisory-analyzer-gaps-are-reclassified",
            ),
            pytest.param(
                GAPS_INFRA_ACTIONABILITY_ADVISORY_AND_BLOCKING,
                ACTIONABILITY_ADVISORY_AND_BLOCKING_RESULT,
                1,
                GAPS_NEXT_PROMPT_USER,
                "feature refinement",
                id="blocking-analyzer-gap-still-prompts",
            ),
        ),
    )
    def test_reclassifies_analyzer_advisory_gaps_before_counting_but_keeps_blocking_gaps(
        self, feature_dir, source_text, actionability_result, expected_gap_count, expected_next, blocking_group
    ):
        staging = feature_dir / ".analysis-infra.md"
        staging.write_text(source_text)
        out_file = feature_dir / "TestPlanGaps.md"

        result = _run_cli(
            "--feature-name",
            "Test Feature",
            "--source-key",
            "RHAISTRAT-400",
            "--source",
            f"infra={staging}",
            "--actionability-result",
            json.dumps(actionability_result),
            "--out",
            str(out_file),
        )

        assert result.returncode == 0, result.stderr
        stdout_data = json.loads(result.stdout)
        assert stdout_data["gap_count"] == expected_gap_count
        assert stdout_data["next"] == expected_next

        frontmatter, body = read_frontmatter(out_file)
        assert frontmatter["gap_count"] == expected_gap_count
        assert "## Advisory Actionability Gaps" in body
        for advisory_gap in actionability_result["advisory_gaps"]:
            assert advisory_gap in body
        assert "- **ADR** — flagged by: infra" not in body
        assert "- **API spec** — flagged by: infra" not in body
        if blocking_group:
            assert f"- **{blocking_group}** — flagged by: infra" in body
            assert "Detailed RBAC role definitions and permission matrices" in body

    @pytest.mark.parametrize(
        "actionability_payload, expected_error",
        (
            pytest.param(
                {"valid": True, "bare_tbd": [], "missing_details": []},
                "advisory_gaps",
                id="missing-advisory-gaps",
            ),
            pytest.param(
                {"valid": True, "bare_tbd": [], "missing_details": [], "advisory_gaps": "not-a-list"},
                "advisory_gaps",
                id="advisory-gaps-not-a-list",
            ),
        ),
    )
    def test_malformed_actionability_payload_fails_before_gap_artifact_write(
        self, feature_dir, actionability_payload, expected_error
    ):
        staging = feature_dir / ".analysis-infra.md"
        staging.write_text("## Gaps\n\nNo gaps identified.\n")
        out_file = feature_dir / "TestPlanGaps.md"

        result = _run_cli(
            "--feature-name",
            "Test Feature",
            "--source-key",
            "RHAISTRAT-400",
            "--source",
            f"infra={staging}",
            "--actionability-result",
            json.dumps(actionability_payload),
            "--out",
            str(out_file),
        )

        assert result.returncode == 1
        error_payload = json.loads(result.stdout)
        assert error_payload["status"] == "failed"
        assert expected_error in error_payload["error"]
        assert not out_file.exists()
        assert staging.exists()

    @pytest.mark.parametrize(
        "sources,expected_gap_count,expected_status,body_contains,body_excludes",
        [
            (
                {
                    "endpoints": GAPS_ENDPOINTS_DUPLICATE,
                    "risks": GAPS_RISKS_DUPLICATE,
                    "infra": GAPS_INFRA_SINGLETON,
                },
                3,
                "Open",
                "# Gaps — Test Feature",
                None,
            ),
            (
                {"endpoints": "## Gaps\n\nNo gaps identified.\n"},
                0,
                "Resolved",
                "No gaps identified.",
                "# Gaps — Test Feature\n\n-",
            ),
        ],
        ids=["gaps-present", "no-gaps"],
    )
    def test_writes_gaps_file_stamps_frontmatter_and_cleans_temp_files(
        self, feature_dir, sources, expected_gap_count, expected_status, body_contains, body_excludes
    ):
        source_files = {}
        for name, content in sources.items():
            path = feature_dir / f".analysis-{name}.md"
            path.write_text(content)
            source_files[name] = path
        out_file = feature_dir / "TestPlanGaps.md"

        source_args = []
        for name, path in source_files.items():
            source_args += ["--source", f"{name}={path}"]

        result = _run_cli(
            "--feature-name",
            "Test Feature",
            "--source-key",
            "RHAISTRAT-400",
            *source_args,
            "--out",
            str(out_file),
        )

        assert result.returncode == 0, result.stderr
        stdout_data = json.loads(result.stdout)
        expected_next = GAPS_NEXT_PROMPT_USER if expected_gap_count > 0 else GAPS_NEXT_PROCEED
        assert stdout_data == {
            "gap_count": expected_gap_count,
            "status": expected_status,
            "next": expected_next,
        }

        frontmatter, body = read_frontmatter(out_file)
        assert frontmatter["feature"] == "Test Feature"
        assert frontmatter["source_key"] == "RHAISTRAT-400"
        assert frontmatter["status"] == expected_status
        assert frontmatter["gap_count"] == expected_gap_count
        assert frontmatter["last_updated"] == LAST_UPDATED
        assert body_contains in body
        if body_excludes:
            assert body_excludes not in body

        for path in source_files.values():
            assert not path.exists()

    def test_missing_source_file_exits_nonzero_before_writing_output(self, feature_dir):
        out_file = feature_dir / "TestPlanGaps.md"
        nonexistent = feature_dir / ".analysis-endpoints.md"

        result = _run_cli(
            "--feature-name",
            "Test Feature",
            "--source-key",
            "RHAISTRAT-400",
            "--source",
            f"endpoints={nonexistent}",
            "--out",
            str(out_file),
        )

        assert result.returncode != 0
        stdout_data = json.loads(result.stdout)
        assert stdout_data == {"status": "failed", "error": "source_file_not_found"}
        assert not out_file.exists()

    def test_cleanup_preserves_testplan_gaps_when_source_is_out_path(self, feature_dir):
        out_file = feature_dir / "TestPlanGaps.md"
        out_file.write_text(GAPS_ENDPOINTS_DUPLICATE)

        result = _run_cli(
            "--feature-name",
            "Test Feature",
            "--source-key",
            "RHAISTRAT-400",
            "--source",
            f"endpoints={out_file}",
            "--out",
            str(out_file),
        )

        assert result.returncode == 0, result.stderr
        assert out_file.exists()
        assert "gap_count" in json.loads(result.stdout)

    def test_cleanup_skips_unverified_source_outside_feature_dir(self, feature_dir):
        outsider = feature_dir.parent / "outside-source.md"
        outsider.write_text(GAPS_ENDPOINTS_DUPLICATE)
        out_file = feature_dir / "TestPlanGaps.md"

        result = _run_cli(
            "--feature-name",
            "Test Feature",
            "--source-key",
            "RHAISTRAT-400",
            "--source",
            f"endpoints={outsider}",
            "--out",
            str(out_file),
        )

        assert result.returncode == 0, result.stderr
        assert outsider.exists()
        assert out_file.exists()

    @pytest.mark.parametrize(
        "env_overrides",
        [{"CI": "true"}, {"CLAUDE_NON_INTERACTIVE": "true"}],
        ids=["ci", "claude-non-interactive"],
    )
    def test_gaps_present_non_interactive_next_is_proceed(self, feature_dir, env_overrides):
        staging = feature_dir / ".analysis-endpoints.md"
        staging.write_text(GAPS_ENDPOINTS_DUPLICATE)
        out_file = feature_dir / "TestPlanGaps.md"

        result = _run_cli(
            "--feature-name",
            "Test Feature",
            "--source-key",
            "RHAISTRAT-400",
            "--source",
            f"endpoints={staging}",
            "--out",
            str(out_file),
            env_overrides=env_overrides,
        )

        assert result.returncode == 0, result.stderr
        stdout_data = json.loads(result.stdout)
        assert stdout_data["gap_count"] > 0
        assert stdout_data["next"] == GAPS_NEXT_PROCEED

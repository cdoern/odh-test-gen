"""Unit tests for scripts/consolidate_gaps_and_stamp.py staging-file cleanup."""

from pathlib import Path

import pytest

from scripts.consolidate_gaps_and_stamp import (
    _resolve_last_updated,
    _verified_staging_path,
    consolidate_and_stamp,
    decide_gaps_next,
)
from tests.consts.gaps_constants import (
    ACTIONABILITY_CONCERN_CLASSIFICATION_CASES,
    GAPS_ALL_EMPTY,
    GAPS_ENDPOINTS_DUPLICATE,
    GAPS_NEXT_PROCEED,
    GAPS_NEXT_PROMPT_USER,
)
from tests.consts.validation_constants import ACTIONABILITY_ADVISORY_RESULT

LAST_UPDATED = "1999-12-31"


class TestVerifiedStagingPath:
    def test_stamp_verified_path_accepts_expected_analysis_file(self, tmp_path):
        out_path = tmp_path / "TestPlanGaps.md"
        staging = tmp_path / ".analysis-endpoints.md"
        staging.write_text("unused")

        result = _verified_staging_path("endpoints", str(staging), str(out_path))
        assert result is not None
        assert result.name == ".analysis-endpoints.md"
        assert result.resolve() == staging.resolve()

    def test_stamp_verified_path_accepts_relative_path_to_expected_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        out_path = Path("TestPlanGaps.md")
        staging = Path(".analysis-risks.md")
        staging.write_text("unused")

        result = _verified_staging_path("risks", str(staging), str(out_path))

        assert result is not None
        assert result.name == ".analysis-risks.md"
        assert result.resolve() == staging.resolve()

    @pytest.mark.parametrize(
        "name,path_factory,out_name",
        [
            (
                "endpoints",
                lambda feature: feature / "TestPlanGaps.md",
                "TestPlanGaps.md",
            ),
            (
                "endpoints",
                lambda feature: feature.parent / "outside.md",
                "TestPlanGaps.md",
            ),
            (
                "endpoints",
                lambda feature: feature / "not-a-staging-file.md",
                "TestPlanGaps.md",
            ),
            (
                "endpoints",
                lambda feature: feature / ".analysis-risks.md",
                "TestPlanGaps.md",
            ),
            (
                "foo/bar",
                lambda feature: feature / ".analysis-foo/bar.md",
                "TestPlanGaps.md",
            ),
            (
                "..",
                lambda feature: feature / ".analysis-...md",
                "TestPlanGaps.md",
            ),
        ],
        ids=[
            "resolves-to-out-path",
            "outside-feature-dir",
            "unexpected-filename",
            "wrong-analyzer-staging-name",
            "name-with-slash",
            "dotdot-name",
        ],
    )
    def test_stamp_verified_path_skips_unverified_sources(self, tmp_path, name, path_factory, out_name):
        feature_dir = tmp_path / "feature"
        feature_dir.mkdir()
        out_path = feature_dir / out_name
        out_path.write_text("gaps")
        source_path = path_factory(feature_dir)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        if not source_path.exists():
            source_path.write_text("payload")

        assert _verified_staging_path(name, str(source_path), str(out_path)) is None

    def test_stamp_verified_path_skips_symlink_to_out_path(self, tmp_path):
        out_path = tmp_path / "TestPlanGaps.md"
        out_path.write_text("generated")
        staging = tmp_path / ".analysis-endpoints.md"
        staging.symlink_to(out_path)

        assert _verified_staging_path("endpoints", str(staging), str(out_path)) is None

    def test_stamp_verified_path_skips_traversal_escape(self, tmp_path):
        feature_dir = tmp_path / "feature"
        feature_dir.mkdir()
        secret = tmp_path / ".analysis-endpoints.md"
        secret.write_text("must not be deleted")
        out_path = feature_dir / "TestPlanGaps.md"

        escaped = feature_dir / ".." / ".analysis-endpoints.md"

        assert _verified_staging_path("endpoints", str(escaped), str(out_path)) is None


class TestConsolidateAndStampCleanup:
    def test_stamp_cleanup_deletes_verified_staging_file(self, tmp_path):
        staging = tmp_path / ".analysis-endpoints.md"
        staging.write_text(GAPS_ENDPOINTS_DUPLICATE)
        out_path = tmp_path / "TestPlanGaps.md"

        consolidate_and_stamp(
            "Test Feature",
            "RHAISTRAT-400",
            [f"endpoints={staging}"],
            str(out_path),
            last_updated=LAST_UPDATED,
        )

        assert out_path.exists()
        assert not staging.exists()

    def test_stamp_cleanup_preserves_out_path_when_used_as_source(self, tmp_path):
        out_path = tmp_path / "TestPlanGaps.md"
        out_path.write_text(GAPS_ALL_EMPTY)

        result = consolidate_and_stamp(
            "Test Feature",
            "RHAISTRAT-400",
            [f"endpoints={out_path}"],
            str(out_path),
            last_updated=LAST_UPDATED,
        )

        assert result["status"] == "Resolved"
        assert out_path.exists()
        assert "No gaps identified." in out_path.read_text()

    def test_stamp_cleanup_skips_unverified_source_and_deletes_verified(self, tmp_path):
        feature_dir = tmp_path / "feature"
        feature_dir.mkdir()
        verified = feature_dir / ".analysis-endpoints.md"
        verified.write_text(GAPS_ENDPOINTS_DUPLICATE)
        outsider = tmp_path / "outside-source.md"
        outsider.write_text(GAPS_ALL_EMPTY)
        unexpected = feature_dir / "notes.md"
        unexpected.write_text(GAPS_ALL_EMPTY)
        out_path = feature_dir / "TestPlanGaps.md"

        consolidate_and_stamp(
            "Test Feature",
            "RHAISTRAT-400",
            [
                f"endpoints={verified}",
                f"risks={outsider}",
                f"infra={unexpected}",
            ],
            str(out_path),
            last_updated=LAST_UPDATED,
        )

        assert out_path.exists()
        assert not verified.exists()
        assert outsider.exists()
        assert unexpected.exists()


class TestConsolidateAndStampSourceErrors:
    @pytest.mark.parametrize(
        "make_source_args,expected_error",
        [
            (lambda path: [f"endpoints={path}"], "source_file_not_found"),
            (lambda _path: ["endpoints"], "invalid_source_argument"),
        ],
        ids=["missing-file", "malformed-argument"],
    )
    def test_propagates_source_read_error(self, tmp_path, make_source_args, expected_error):
        missing = tmp_path / ".analysis-endpoints.md"
        out_path = tmp_path / "TestPlanGaps.md"

        with pytest.raises(ValueError, match=expected_error):
            consolidate_and_stamp(
                "Test Feature",
                "RHAISTRAT-400",
                make_source_args(missing),
                str(out_path),
                last_updated=LAST_UPDATED,
            )

        assert not out_path.exists()


class TestActionabilityAdvisoryConcernClassification:
    @pytest.mark.parametrize(
        "concern, resolved_by, expected_gap_count, expected_advisory",
        ACTIONABILITY_CONCERN_CLASSIFICATION_CASES,
        ids=(
            "hf-token-scope-is-material-api-spec-gap",
            "strict-test-data-format-example-is-advisory",
            "compound-test-data-and-hf-concern-is-material",
            "version-and-build",
            "data-schema-and-example",
            "api-response-schema",
            "data-request-contract",
        ),
    )
    def test_classifies_advisory_vocabulary_without_hiding_material_gaps(
        self, tmp_path, concern, resolved_by, expected_gap_count, expected_advisory
    ):
        staging = tmp_path / ".analysis-infra.md"
        staging.write_text(f"## Gaps\n\n- **{concern}** — would be resolved by: {resolved_by}\n")
        out_path = tmp_path / "TestPlanGaps.md"

        result = consolidate_and_stamp(
            "Test Feature",
            "RHAISTRAT-400",
            [f"infra={staging}"],
            str(out_path),
            last_updated=LAST_UPDATED,
            actionability_result=ACTIONABILITY_ADVISORY_RESULT,
        )

        assert result["gap_count"] == expected_gap_count
        body = out_path.read_text()
        if expected_advisory:
            assert f"- {concern} (analyzer advisory;" in body
            assert f"- **{resolved_by}** — flagged by: infra" not in body
        else:
            assert f"- **{resolved_by}** — flagged by: infra" in body
            assert f"  - {concern}" in body


class TestResolveLastUpdated:
    def test_prefers_explicit_value(self, monkeypatch):
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")

        assert _resolve_last_updated(LAST_UPDATED) == LAST_UPDATED

    def test_derives_utc_date_from_source_date_epoch(self, monkeypatch):
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")

        assert _resolve_last_updated(None) == "1970-01-01"

    @pytest.mark.parametrize("raw", [None, "", "not-an-epoch"])
    def test_raises_when_neither_explicit_nor_valid_epoch(self, monkeypatch, raw):
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
        if raw is not None:
            monkeypatch.setenv("SOURCE_DATE_EPOCH", raw)

        with pytest.raises(ValueError, match="last_updated_required"):
            _resolve_last_updated(None)


class TestDecideGapsNext:
    @pytest.mark.parametrize(
        "gap_count,interactive,expected",
        [
            (0, True, GAPS_NEXT_PROCEED),
            (0, False, GAPS_NEXT_PROCEED),
            (1, True, GAPS_NEXT_PROMPT_USER),
            (1, False, GAPS_NEXT_PROCEED),
            (5, True, GAPS_NEXT_PROMPT_USER),
            (5, False, GAPS_NEXT_PROCEED),
        ],
        ids=[
            "zero-interactive",
            "zero-non-interactive",
            "one-interactive",
            "one-non-interactive",
            "many-interactive",
            "many-non-interactive",
        ],
    )
    def test_prompt_user_only_when_gaps_exist_and_session_is_interactive(self, gap_count, interactive, expected):
        assert decide_gaps_next(gap_count, interactive=interactive) == expected

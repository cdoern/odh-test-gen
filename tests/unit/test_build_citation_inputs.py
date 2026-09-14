"""Unit tests for build_citation_inputs — deterministic construction of the citation gate's
inputs (ac_count/nfr_categories + validator results) from a resolved strategy file, or none.
"""

import json
import re
import sys

import pytest

from scripts.build_citation_inputs import build_citation_inputs, main
from scripts.utils.schemas import TEMPLATE_HEADINGS
from tests.consts.test_plan_constants import TESTPLAN_INTERFACE_COVERAGE_UI_ONLY_6_2
from tests.consts.validation_constants import ACTIONABILITY_ADVISORY_GAPS_PLAN
from tests.helpers import objectives_citing_every_ac, write_testplan_with_objectives

E2E_OR_UI_DIAGNOSTIC_KEY = "missing_e2e_or_ui_in_6_2"

STRATEGY_CONTENT = (
    "h3. Acceptance Criteria\n\n"
    "# Given a user registers a store, then it persists\n"
    "# Given a duplicate name, then it is rejected\n\n"
    "h3. Non-Functional Requirements\n\n"
    "* *Upgrade*: GET endpoints keep their shape\n"
)


class TestBuildCitationInputs:
    def test_interface_coverage_exposes_renamed_e2e_or_ui_diagnostic(self, tmp_path):
        (tmp_path / "TestPlan.md").write_text(TESTPLAN_INTERFACE_COVERAGE_UI_ONLY_6_2)
        strategy_file = tmp_path / ".source-strategy.md"
        strategy_file.write_text(STRATEGY_CONTENT)

        result = build_citation_inputs(str(tmp_path), str(strategy_file))
        interface_coverage = result["interface_coverage_result"]

        assert interface_coverage["valid"] is True
        assert interface_coverage[E2E_OR_UI_DIAGNOSTIC_KEY] == []

    def test_ok_path_computes_ac_count_and_validator_results(self, tmp_path):
        write_testplan_with_objectives(tmp_path / "TestPlan.md", objectives_citing_every_ac(2, ["Upgrade"]))
        strategy_file = tmp_path / ".source-strategy.md"
        strategy_file.write_text(STRATEGY_CONTENT)

        result = build_citation_inputs(str(tmp_path), str(strategy_file))

        assert result["status"] == "ok"
        assert result["ac_citations_result"]["valid"] is True
        assert result["ac_coverage_result"]["valid"] is True
        assert result["ac_coverage_result"]["ac_count"] == 2
        assert result["interface_coverage_result"]["valid"] is True
        assert result["scope_coverage_result"]["valid"] is True
        assert result["actionability_result"]["valid"] is False

    def test_quality_gate_inputs_detect_missing_strategy_requirement_and_actionability_gaps(self, tmp_path):
        write_testplan_with_objectives(
            tmp_path / "TestPlan.md",
            "1. Verify registration (AC: #1 — registration succeeds)\n"
            f"\n{TEMPLATE_HEADINGS['3.1']}\n\n"
            "OpenShift version: TBD\n"
            "RHOAI version: TBD\n"
            f"\n{TEMPLATE_HEADINGS['3.3']}\n\n"
            "Admin user for setup\n",
        )
        strategy_file = tmp_path / ".source-strategy.md"
        strategy_file.write_text(
            "h3. Acceptance Criteria\n\n"
            "# Given a user registers a store, then it persists\n\n"
            "h3. Non-Functional Requirements\n\n"
            "* *Upgrade*: GET endpoints keep their shape\n"
        )

        result = build_citation_inputs(str(tmp_path), str(strategy_file))

        assert result["scope_coverage_result"]["valid"] is False
        assert result["scope_coverage_result"]["missing"]
        assert result["actionability_result"]["valid"] is False
        assert "OpenShift version" in result["actionability_result"]["bare_tbd"]
        assert "RBAC roles and permissions" in result["actionability_result"]["missing_details"]

    def test_quality_gate_inputs_allow_tbd_only_with_resolution_path_and_concrete_rbac(self, tmp_path):
        write_testplan_with_objectives(
            tmp_path / "TestPlan.md",
            "1. Verify registration (AC: #1 — registration succeeds)\n"
            f"\n{TEMPLATE_HEADINGS['3.1']}\n\n"
            "OpenShift version: TBD — Resolution: retrieve the supported-platform matrix from "
            "platform engineering before setup.\n"
            "RHOAI version: 2.25\n"
            f"\n{TEMPLATE_HEADINGS['3.2']}\n\n"
            "Registration payload: JSON object with a unique store name and reachable endpoint, "
            'for example {"name": "orders", "endpoint": "https://store.example"}.\n'
            f"\n{TEMPLATE_HEADINGS['3.3']}\n\n"
            "| Role | Resource | Permissions |\n"
            "|------|----------|-------------|\n"
            "| Admin | vector-store resources | create, read, delete |\n",
        )
        strategy_file = tmp_path / ".source-strategy.md"
        strategy_file.write_text("h3. Acceptance Criteria\n\n# Given a user registers a store, then it persists\n")

        result = build_citation_inputs(str(tmp_path), str(strategy_file))

        assert result["actionability_result"]["valid"] is True
        assert result["actionability_result"]["bare_tbd"] == []
        assert result["actionability_result"]["missing_details"] == []

    def test_quality_gate_inputs_preserve_advisory_actionability_gaps(self, tmp_path):
        write_testplan_with_objectives(
            tmp_path / "TestPlan.md",
            f"1. Verify registration (AC: #1 — registration succeeds)\n\n{ACTIONABILITY_ADVISORY_GAPS_PLAN}",
        )
        strategy_file = tmp_path / ".source-strategy.md"
        strategy_file.write_text("h3. Acceptance Criteria\n\n# Given a user registers a store, then it persists\n")

        result = build_citation_inputs(str(tmp_path), str(strategy_file))

        actionability = result["actionability_result"]
        assert actionability["valid"] is True
        assert {
            "OpenShift version",
            "RHOAI version",
            "test data formats and examples",
        } <= set(actionability["advisory_gaps"])
        assert actionability["bare_tbd"] == []
        assert actionability["missing_details"] == []

    def test_missing_testplan_is_an_ordinary_invalid_result_not_an_execution_failure(self, tmp_path):
        strategy_file = tmp_path / ".source-strategy.md"
        strategy_file.write_text(STRATEGY_CONTENT)

        result = build_citation_inputs(str(tmp_path), str(strategy_file))  # no TestPlan.md written

        assert result["status"] == "ok"
        assert result["ac_citations_result"]["valid"] is False
        assert "error" in result["ac_citations_result"]

    def test_directory_path_fails_filename_check(self, tmp_path):
        write_testplan_with_objectives(tmp_path / "TestPlan.md", "1. Verify something (AC: #1 — cited)\n")

        # A directory path fails the require_feature_snapshot filename check before the read is
        # attempted.
        with pytest.raises(ValueError, match=re.escape("snapshot filename must be .source-strategy.md")):
            build_citation_inputs(str(tmp_path), str(tmp_path))


class TestBuildCitationInputsCLI:
    def test_ok_path_prints_status_ok_and_exits_zero(self, tmp_path, capsys):
        write_testplan_with_objectives(tmp_path / "TestPlan.md", objectives_citing_every_ac(2, ["Upgrade"]))
        strategy_file = tmp_path / ".source-strategy.md"
        strategy_file.write_text(STRATEGY_CONTENT)

        old_argv = sys.argv
        try:
            sys.argv = ["build_citation_inputs.py", str(tmp_path), "--strategy-file", str(strategy_file)]
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
        assert output["ac_citations_result"]["valid"] is True
        assert output["ac_coverage_result"]["valid"] is True
        assert output["ac_coverage_result"]["ac_count"] == 2
        assert output["interface_coverage_result"]["valid"] is True
        assert output["scope_coverage_result"]["valid"] is True
        assert output["actionability_result"]["valid"] is False

    def test_execution_failure_exits_one_with_error_status(self, tmp_path, capsys):
        write_testplan_with_objectives(tmp_path / "TestPlan.md", "1. Verify something (AC: #1 — cited)\n")

        old_argv = sys.argv
        try:
            sys.argv = ["build_citation_inputs.py", str(tmp_path), "--strategy-file", str(tmp_path)]
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 1
            else:
                raise AssertionError("main() must exit with code 1")
        finally:
            sys.argv = old_argv

        output = json.loads(capsys.readouterr().out)
        assert output["status"] == "error"
        assert isinstance(output["error"], str) and output["error"]


class TestBuildCitationInputsContainment:
    """Verify that require_feature_snapshot + read_file_nofollow reject unsafe strategy_file
    paths — symlinks pointing outside feature_dir and wrong filenames.
    """

    def test_rejects_symlink_pointing_outside_feature_dir(self, tmp_path):
        # feature_dir is a subdirectory of tmp_path; the symlink target sits OUTSIDE it (a
        # sibling directory).  resolve() dereferences the symlink, so require_feature_snapshot
        # sees a path outside feature_dir and raises ValueError.
        feature_dir = tmp_path / "feature"
        feature_dir.mkdir()
        write_testplan_with_objectives(feature_dir / "TestPlan.md", "1. Verify something (AC: #1 — cited)\n")
        outside = tmp_path / "outside"
        outside.mkdir()
        real_file = outside / ".source-strategy.md"
        real_file.write_text(STRATEGY_CONTENT)
        link = feature_dir / ".source-strategy.md"
        link.symlink_to(real_file)

        with pytest.raises(ValueError, match="not inside feature_dir"):
            build_citation_inputs(str(feature_dir), str(link))

    def test_rejects_wrong_filename(self, tmp_path):
        write_testplan_with_objectives(tmp_path / "TestPlan.md", "1. Verify something (AC: #1 — cited)\n")
        wrong_name = tmp_path / "strategy.md"
        wrong_name.write_text(STRATEGY_CONTENT)

        with pytest.raises(ValueError, match=re.escape("snapshot filename must be .source-strategy.md")):
            build_citation_inputs(str(tmp_path), str(wrong_name))

    def test_symlink_outside_feature_dir_cli_exits_one(self, tmp_path, capsys):
        # feature_dir is a subdirectory of tmp_path; the symlink target sits OUTSIDE it.
        feature_dir = tmp_path / "feature"
        feature_dir.mkdir()
        write_testplan_with_objectives(feature_dir / "TestPlan.md", "1. Verify something (AC: #1 — cited)\n")
        outside = tmp_path / "outside"
        outside.mkdir()
        real_file = outside / ".source-strategy.md"
        real_file.write_text(STRATEGY_CONTENT)
        link = feature_dir / ".source-strategy.md"
        link.symlink_to(real_file)

        old_argv = sys.argv
        try:
            sys.argv = ["build_citation_inputs.py", str(feature_dir), "--strategy-file", str(link)]
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 1
            else:
                raise AssertionError("main() must exit with code 1")
        finally:
            sys.argv = old_argv

        output = json.loads(capsys.readouterr().out)
        assert output == {"status": "error", "error": "citation_input_construction_failed"}

    def test_wrong_filename_cli_exits_one(self, tmp_path, capsys):
        write_testplan_with_objectives(tmp_path / "TestPlan.md", "1. Verify something (AC: #1 — cited)\n")
        wrong_name = tmp_path / "strategy.md"
        wrong_name.write_text(STRATEGY_CONTENT)

        old_argv = sys.argv
        try:
            sys.argv = ["build_citation_inputs.py", str(tmp_path), "--strategy-file", str(wrong_name)]
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 1
            else:
                raise AssertionError("main() must exit with code 1")
        finally:
            sys.argv = old_argv

        output = json.loads(capsys.readouterr().out)
        assert output == {"status": "error", "error": "citation_input_construction_failed"}

    def test_rejects_symlink_to_target_inside_feature_dir(self, tmp_path):
        # Pins the is_symlink() branch in require_feature_snapshot
        # The symlink target is INSIDE feature_dir
        feature_dir = tmp_path / "feature"
        feature_dir.mkdir()
        write_testplan_with_objectives(feature_dir / "TestPlan.md", "1. Verify something (AC: #1 — cited)\n")
        real_file = feature_dir / "real-strategy.md"
        real_file.write_text(STRATEGY_CONTENT)
        link = feature_dir / ".source-strategy.md"
        link.symlink_to(real_file)

        with pytest.raises(ValueError, match="is a symlink"):
            build_citation_inputs(str(feature_dir), str(link))

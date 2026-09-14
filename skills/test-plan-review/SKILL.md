---
name: test-plan-review
description: Reviews a generated test plan for completeness, consistency, and quality using a 5-criteria rubric. Scores, auto-revises, and re-scores (max 2 cycles). Use for automated quality assessment and iterative improvement of generated test plans.
user-invocable: false
model: opus
allowedTools:
  - Read
  - Write
  - Bash
  - Glob
  - Skill
---

# Test Plan Reviewer

Internal orchestrator that reviews and scores a test plan using the quality rubric (5 criteria, 0-2 each, 10-point scale). Auto-revises failing plans and re-scores up to 2 times.

## Usage

This skill is not user-invocable. It is called by:
- `test-plan.create` (Step 4)
- automation/orchestrator flows that need score + auto-revision behavior

## Inputs

### From arguments
Parse `$ARGUMENTS` to extract:
1. **Feature directory** (required): path to directory containing `TestPlan.md`

### Auto-detection
If no arguments provided and `test-plan.create` just generated a test plan in this session, use that feature directory automatically.

## Process

### Step 0: Python dependencies

Install the test-plan package (makes all scripts importable):
```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv sync --extra dev)
```

If installation fails, inform the user and do NOT proceed. Once installed, all Python scripts will work from any directory.

### Step 1: Read Test Plan and Resolve Source Strategy

1. Read `<feature_dir>/TestPlan.md`
2. Read frontmatter to extract `source_key`:
   ```bash
   source_key=$(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && \
                uv run python scripts/frontmatter.py read <feature_dir>/TestPlan.md source_key)
   ```
3. Resolve the source strategy via the shared resolver — snapshot-primary: reads
   `<feature_dir>/.source-strategy.md` if `test-plan.create` already saved one, otherwise fetches
   from Jira and saves it there for next time. No degraded mode: if neither is available, this is
   a hard failure.
   ```bash
   repo_root=$(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel)
   resolve_result=$(cd "$repo_root" && uv run python scripts/resolve_strategy.py <feature_dir> "$source_key")
   resolve_exit=$?

   if [ "$resolve_exit" -ne 0 ]; then
       echo "ERROR: scripts/resolve_strategy.py failed to resolve the source strategy — stopping review." >&2
       echo "$resolve_result" >&2
       exit 1
   fi

   strategy_file_path=$(echo "$resolve_result" | jq -r '.strategy_file')
   ```

   `strategy_file_path` is the persistent, local-only snapshot — it is never removed (not at Step
   5, not across any re-score cycle) and is reused as-is on every re-score in Step 4e.

4. Compute interface coverage, AC/NFR citation validity, bidirectional scope coverage, and actionability evidence deterministically (these are mechanical checks — none is an LLM judgment call). This is delegated to [`scripts/build_citation_inputs.py`](scripts/build_citation_inputs.py), which derives `ac_count`/`nfr_categories` from `strategy_file_path` and calls the validators directly:

   ```bash
   gate_result=$(cd "$repo_root" && uv run python scripts/build_citation_inputs.py <feature_dir> --strategy-file "$strategy_file_path") || {
       echo "ERROR: scripts/build_citation_inputs.py failed to construct citation gate inputs — stopping review." >&2
       echo "$gate_result" >&2
       exit 1
   }

   interface_coverage_result=$(echo "$gate_result" | jq -c '.interface_coverage_result')
   ac_citations_result=$(echo "$gate_result" | jq -c '.ac_citations_result')
   ac_coverage_result=$(echo "$gate_result" | jq -c '.ac_coverage_result')
   scope_coverage_result=$(echo "$gate_result" | jq -c '.scope_coverage_result')
   actionability_result=$(echo "$gate_result" | jq -c '.actionability_result')
   ```

   A nonzero exit means gate-input construction itself failed (unreadable strategy file, a parsing bug) — that's an execution failure, not data about the test plan, so stop rather than silently falling back to degraded mode. With the pre-create-cases guards, `valid: true` is expected before test cases exist — both Section 9.2 (Test Cases column blank) and Section 6.2 are recognized as not-yet-populated and skipped. Once Section 6.2 is populated, `missing_e2e_or_ui_in_6_2` identifies declared, non-pending interfaces with a populated row that lacks both a `TC-E2E-*` and a `TC-UI-*` reference; each populated row must contain at least one `TC-E2E-*` or `TC-UI-*` reference. `missing_in_6_2` continues to identify absent or blank/placeholder interface rows. The actionability payload's `valid` field reflects only blocking evidence (`bare_tbd` and `missing_details`); `advisory_gaps` records missing or vague versions and incomplete test-data examples for visibility. Pass both kinds of actionability evidence to the score agent. Section 3.1 must contain substantive environment/configuration evidence; a heading or vague/unavailable-only statement remains blocking even when it is non-empty. The validator applies the same occurrence-level TBD classifier to Sections 3.1, 3.2, and 3.3: a grounded `TBD — Resolution: ...` path is allowed, including `derive` from a named overlay requirement, but a bare or unresolved TBD remains blocking. RBAC evidence must identify a role, permissions, and a concrete resource; `all`/`any`/`every` collections and wildcard resources are not concrete. Examples count only in explicit example labels/table columns or `e.g.,`/`for example` clauses.

5. Resolve `additional_docs` from TestPlan.md frontmatter deterministically — path validation and file reading happen in Python, not in the LLM prompt. The script reads frontmatter itself (the LLM is not in the trust path for path resolution):

   ```bash
   additional_docs_raw=$(cd "$repo_root" && uv run python scripts/resolve_additional_docs.py <feature_dir>) || {
       echo "ERROR: scripts/resolve_additional_docs.py failed — stopping review." >&2
       echo "$additional_docs_raw" >&2
       exit 1
   }

   additional_docs_result=$(echo "$additional_docs_raw" | jq -c '.docs')
   ```

6. Run the deterministic scope and boilerplate checks. These flag out-of-scope test levels
   (Section 2.1) and generic boilerplate language (Sections 1.3/2.3/8) without an LLM call —
   results feed the SCOPE FIDELITY and SPECIFICITY rubric criteria in Step 2. Team-specific
   pattern overrides are resolved from the TestPlan.md `components` frontmatter, mapped to
   `COMPONENT_TEST_DIR_MAP` team names via `get_component_test_dir.py --teams-only`:

   ```bash
   team_list=$(cd "$repo_root" && uv run python scripts/get_component_test_dir.py --teams-only <feature_dir>) || {
       echo "ERROR: scripts/get_component_test_dir.py --teams-only failed — stopping review." >&2
       echo "$team_list" >&2
       exit 1
   }

   scope_check_result=$(cd "$repo_root" && uv run python scripts/validate_test_scope.py <feature_dir>/TestPlan.md \
       --include-teams="$team_list" --checks-dir=scripts/checks) || {
       echo "ERROR: scripts/validate_test_scope.py failed — stopping review." >&2
       echo "$scope_check_result" >&2
       exit 1
   }

   boilerplate_result=$(cd "$repo_root" && uv run python scripts/detect_boilerplate.py <feature_dir>/TestPlan.md \
       --include-teams="$team_list" --checks-dir=scripts/checks) || {
       echo "ERROR: scripts/detect_boilerplate.py failed — stopping review." >&2
       echo "$boilerplate_result" >&2
       exit 1
   }
   ```

   `validate_test_scope.py`/`detect_boilerplate.py` always exit 0 by design (results are JSON,
   not pass/fail signals) — a nonzero exit here means the script itself crashed (bad path,
   malformed config), an execution failure worth stopping for, same treatment as the other
   Step 1 scripts.

### Step 2: Score (fork)

Load calibration examples (fail closed — stop on nonzero exit). Adding a pair is dropping a
file in `calibration/core/`, optional `calibration/ui/`, or `calibration/<team>/`; do not edit
this skill for new examples.

```bash
calibration_raw=$(cd "$repo_root" && uv run python scripts/load_calibration.py \
    "${CLAUDE_SKILL_DIR}/calibration" --include-teams="$team_list") || {
    echo "ERROR: scripts/load_calibration.py failed — stopping review." >&2
    echo "$calibration_raw" >&2
    exit 1
}

calibration_text=$(printf '%s\n' "$calibration_raw" | jq -r '.calibration_text')
echo "$calibration_raw" | jq -r '.warnings[]?' >&2
```

Read the score agent prompt from `${CLAUDE_SKILL_DIR}/prompts/score-agent.md`.

Launch a **forked** score agent with these substitutions:
- `{FEATURE_DIR}` = feature directory path
- `{TEST_PLAN_PATH}` = `<feature_dir>/TestPlan.md`
- `{STRATEGY_FILE_PATH}` = `strategy_file_path` from Step 1
- `{CALIBRATION_TEXT}` = `calibration_text` from `load_calibration.py` above
- `{INTERFACE_COVERAGE_RESULT}` = JSON from Step 1 (`interface_coverage_result`)
- `{AC_CITATIONS_RESULT}` = JSON from Step 1 (`ac_citations_result`)
- `{AC_COVERAGE_RESULT}` = JSON from Step 1 (`ac_coverage_result`)
- `{SCOPE_COVERAGE_RESULT}` = JSON from Step 1 (`scope_coverage_result`)
- `{ACTIONABILITY_RESULT}` = JSON from Step 1 (`actionability_result`)
- `{ADDITIONAL_DOCS_CONTENT}` = JSON from Step 1 (`additional_docs_result`)
- `{SCOPE_CHECK_RESULT}` = JSON from Step 1 (`scope_check_result`)
- `{BOILERPLATE_RESULT}` = JSON from Step 1 (`boilerplate_result`)

The score agent evaluates the test plan against a 5-criterion rubric (specificity, grounding, scope fidelity, actionability, consistency) and returns a structured assessment with per-criterion scores and a grounding cross-reference table.

**Completeness checks performed by the score agent:**

| Section | Check |
|---------|-------|
| 1.1 Purpose | Does it clearly state what is being tested and why? |
| 1.2 Scope | Are in-scope and out-of-scope explicitly defined? |
| 1.3 Test Objectives | Is there at least one objective per STRAT acceptance criterion (every AC covered), plus grounded NFR objectives where applicable? |
| 2.1 Test Levels | Are the selected levels appropriate for the feature type? |
| 2.3 Priorities | Are P0/P1/P2 definitions specific to this feature, not generic? |
| 3.1 Cluster Config | Is substantive environment/configuration evidence present, with versions/dependencies specified or unknowns recorded with an explicit resolution path? Vague/unavailable-only content and bare/unresolved TBDs are blocking; missing/vague versions remain advisory when the section is otherwise substantive. |
| 3.2 Test Data | Are test-data requirements concrete enough to act on, with incomplete format/examples retained as advisory gaps? |
| 4 Interfaces Under Test | Are entries grounded in source documents, not fabricated? |
| 6.1 E2E Scenarios | Is the E2E Scenario Summary populated with TC-E2E-* entries? (Note: expected to be empty until create-cases runs) |
| 6.2 E2E Coverage | Does each non-pending interface from Section 4 have at least one `TC-E2E-*` or `TC-UI-*` reference in each populated Section 6.2 row? Checked deterministically via `interface-coverage` (Step 1), not LLM table-reading. (Note: expected to be empty until create-cases runs) |
| 7.1 Disconnected | Addressed with testing considerations or explicitly marked Not Applicable with justification? |
| 7.2 Upgrade | Addressed with testing considerations or explicitly marked Not Applicable with justification? |
| 7.3 Performance | Addressed with testing considerations or explicitly marked Not Applicable with justification? |
| 7.4 RBAC | Addressed with testing considerations or explicitly marked Not Applicable with justification? |
| 7.5 Security | Addressed with testing considerations or explicitly marked Not Applicable with justification? |
| 8 Risks | Are risks specific to this feature, not boilerplate? |
| 9 Environment | Is there enough detail to set up a test environment? |

### Step 3: Review (fork)

Read the review agent prompt from `${CLAUDE_SKILL_DIR}/prompts/review-agent.md`.

Launch a **forked** review agent with these substitutions:
- `{FEATURE_DIR}` = feature directory path
- `{ASSESSMENT_TEXT}` = full output from the score agent (Step 2)
- `{FIRST_PASS}` = `true` (first assessment cycle)

The review agent writes `<feature_dir>/TestPlanReview.md` with rubric scores, feedback, and validated frontmatter.

**Consistency checks performed by the review agent:**
- Do the interfaces in Section 4 align with the scope in Section 1.2?
- Do the test levels in Section 2.1 match the interface types in Section 4?
- Are priority assignments in Section 6.1 consistent with the definitions in Section 2.3?
- Does Section 9.2 list all interfaces from Section 4? (deterministic — from the `interface-coverage` result computed in Step 1, not re-derived)
- Are NFR categories in Section 7 consistent with the feature scope? (e.g., a feature that pulls images should not mark Disconnected as N/A)
- Does Section 6.2 E2E Coverage Matrix include all non-pending interfaces from Section 4 and at least one `TC-E2E-*` or `TC-UI-*` reference per populated interface row? (deterministic — from `missing_in_6_2` and `missing_e2e_or_ui_in_6_2` in the `interface-coverage` result; expected unpopulated until create-cases runs)

### Step 3.5: Enforce Citation Gate

Deterministically re-apply the Scope Fidelity/Specificity caps and Actionability correction the
review agent was instructed to self-apply but might not have — `enforce_citation_gate.py` always
exits 0 and reports outcome as JSON. Blocking Actionability evidence caps a recorded score above
1 to 1/2; valid Actionability never raises a recorded 0/1. The `actionability_capped` result field
is true only when that blocking cap changes the score.

```bash
repo_root=$(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel)
gate_result=$(cd "$repo_root" && uv run python scripts/enforce_citation_gate.py <feature_dir> \
    --ac-citations-result "$ac_citations_result" --ac-coverage-result "$ac_coverage_result" \
    --scope-check-result "$scope_check_result" --boilerplate-result "$boilerplate_result" \
    --scope-coverage-result "$scope_coverage_result" --actionability-result "$actionability_result")
gate_status=$(echo "$gate_result" | jq -r '.status')

case "$gate_status" in
    overridden|ok|skip) ;;
    *)
        echo "ERROR: scripts/enforce_citation_gate.py failed — stopping review." >&2
        echo "$gate_result" >&2
        exit 1
        ;;
esac
```

If `overridden`, Step 4 evaluates the corrected scores/feedback note, not the review agent's own numbers. Anything other than `overridden`/`ok`/`skip` means the gate itself failed to run — stop.

### Step 4: Check Criteria and Revise (max 2 cycles)

After the review agent completes, read the review frontmatter:

```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/frontmatter.py read <feature_dir>/TestPlanReview.md)
```

If all five criteria in `scores.*` are `2`, proceed to Step 5 (done). This can be a Ready result
even when `actionability_result.advisory_gaps` is non-empty; advisory actionability gaps are
visible follow-up items, not revision failures.

If any criterion in `scores.*` is `< 2`, enter the revision loop. Do not enter it solely because
`advisory_gaps` contains missing or vague OpenShift/RHOAI versions or incomplete test-data
format/examples.

#### Revision Loop

Initialize cycle counter: `reassess_cycle=0`

**4a. Filter for revision:**

```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/filter_for_revision.py <feature_dir>)
```

If output is `SKIP`, stop the loop and proceed to Step 5.

**4b. Launch revise agent (fork):**

Read the revise agent prompt from `${CLAUDE_SKILL_DIR}/prompts/revise-agent.md`.

Launch with substitutions:
- `{FEATURE_DIR}` = feature directory path
- `{STRATEGY_FILE_PATH}` = `strategy_file_path` from Step 1
- `{ADDITIONAL_DOCS_CONTENT}` = `additional_docs_result` from Step 1 (refreshed by Step 4e on later cycles)

The revise agent edits TestPlan.md (only sections mapped to failing criteria) and sets `auto_revised=true`.

**4c. Check if reassessment is needed:**

```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/frontmatter.py read <feature_dir>/TestPlanReview.md)
```

If `auto_revised` is `false`, the revise agent found nothing to change — stop the loop.

Increment `reassess_cycle`. If `reassess_cycle >= 2`, stop — max cycles reached. Proceed to Step 5.

**4d. Save cumulative state:**

```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/preserve_review_state.py save <feature_dir>)
```

**4e. Re-score:**

Delete the existing review file to force a clean re-assessment:
```bash
rm <feature_dir>/TestPlanReview.md
```

Recompute validation results against the revised `TestPlan.md` — the revise agent (4b) may have edited Section 4, 6.2, 9.2, or citations, so all four must be refreshed before re-scoring:

```bash
repo_root=$(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel)
gate_result=$(cd "$repo_root" && uv run python scripts/build_citation_inputs.py <feature_dir> --strategy-file "$strategy_file_path") || {
    echo "ERROR: scripts/build_citation_inputs.py failed — stopping review." >&2
    echo "$gate_result" >&2
    exit 1
}

interface_coverage_result=$(echo "$gate_result" | jq -c '.interface_coverage_result')
ac_citations_result=$(echo "$gate_result" | jq -c '.ac_citations_result')
ac_coverage_result=$(echo "$gate_result" | jq -c '.ac_coverage_result')
scope_coverage_result=$(echo "$gate_result" | jq -c '.scope_coverage_result')
actionability_result=$(echo "$gate_result" | jq -c '.actionability_result')

additional_docs_raw=$(cd "$repo_root" && uv run python scripts/resolve_additional_docs.py <feature_dir>) || {
    echo "ERROR: scripts/resolve_additional_docs.py failed — stopping review." >&2
    echo "$additional_docs_raw" >&2
    exit 1
}

additional_docs_result=$(echo "$additional_docs_raw" | jq -c '.docs')

team_list=$(cd "$repo_root" && uv run python scripts/get_component_test_dir.py --teams-only <feature_dir>) || {
    echo "ERROR: scripts/get_component_test_dir.py --teams-only failed — stopping review." >&2
    echo "$team_list" >&2
    exit 1
}

scope_check_result=$(cd "$repo_root" && uv run python scripts/validate_test_scope.py <feature_dir>/TestPlan.md \
    --include-teams="$team_list" --checks-dir=scripts/checks) || {
    echo "ERROR: scripts/validate_test_scope.py failed — stopping review." >&2
    echo "$scope_check_result" >&2
    exit 1
}

boilerplate_result=$(cd "$repo_root" && uv run python scripts/detect_boilerplate.py <feature_dir>/TestPlan.md \
    --include-teams="$team_list" --checks-dir=scripts/checks) || {
    echo "ERROR: scripts/detect_boilerplate.py failed — stopping review." >&2
    echo "$boilerplate_result" >&2
    exit 1
}
```

Repeat Step 2 (score agent) with the revised TestPlan.md and the recomputed results.

**4f. Re-review:**

Repeat Step 3 (review agent) with `{FIRST_PASS}=false`, then repeat Step 3.5 (Enforce Citation Gate) against the recomputed results from 4e.

**4g. Restore before_scores and revision history:**

```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/preserve_review_state.py restore <feature_dir>)
```

**4h. Check criteria again:**

Read the review frontmatter. If all criteria are now `2`, stop.
If any criterion remains `< 2` and cycles remain, go back to 4a.
If cycles are exhausted, stop and proceed to Step 5.

### Step 5: Present Results

`strategy_file_path` is the persistent snapshot — leave it in place for future re-review/re-score runs.

Read the final review file and present a summary to the user:

```markdown
## Test Plan Review — {feature_name}

**Score: {score}/10 — Verdict: {verdict}**

| Criterion | Score |
|-----------|-------|
| Specificity | {n}/2 |
| Grounding | {n}/2 |
| Scope Fidelity | {n}/2 |
| Actionability | {n}/2 |
| Consistency | {n}/2 |

{If before_score differs from score:}
**Delta: {before_score} → {score} ({+/-difference})**

{If verdict = Ready:}
The test plan is ready for test case generation. Any `actionability_result.advisory_gaps` remain
visible follow-up items in `TestPlanGaps.md` and do not block this step. Run
`/test-plan-create-cases <feature_dir>` to proceed.

{If verdict = Revise (after max cycles):}
The test plan improved but still has issues. Review `<feature_dir>/TestPlanReview.md` for remaining feedback. Consider providing additional source documents (ADR, API spec) to resolve blocking grounding or operational gaps; advisory actionability gaps alone do not require them.

{If verdict = Rework:}
The test plan needs significant rework. This may indicate the source strategy lacks sufficient detail. Review `<feature_dir>/TestPlanReview.md` for specific issues and provide source documents for blocking grounding or operational gaps; advisory actionability gaps alone do not require them.

{If this plan is already in an open PR and reviewer comments exist:}
Use `/test-plan-resolve-feedback <PR_URL>` to triage and apply PR feedback items.
```

## Anti-hallucination Rules

When reviewing and suggesting improvements, the score agent MUST follow these constraints:

**NEVER**:
- Invent resolution paths for TBDs (e.g., "check version in ADR section 3" when no ADR exists or that section doesn't specify versions)
- Add specific requirements, API endpoints, or version constraints not present in source documents
- Fabricate documentation references ("see design doc for details" when no design doc exists)
- Assume information exists in documents without verifying
- Create specificity improvements by inventing details

**ALWAYS**:
- For `actionability == 2`, retain a genuinely unknown required value only as `TBD — Resolution: {concrete action} from/with/by/before/after/using {named source or timing}`. The resolution path must be grounded in an actual source or a known owner/timing; `derive` is valid when the named source grounds the derivation. Apply this rule independently to each TBD in Sections 3.1, 3.2, and 3.3. Missing or vague OpenShift/RHOAI versions and incomplete test-data format/examples may remain as advisory gaps and do not by themselves prevent Actionability 2/2.
- Ground all improvements in actual source document content (strategy, ADR, additional_docs)
- Keep bare/unresolved TBDs, missing or non-substantive Section 3.1 environment/configuration, and unusable or broad-collection RBAC evidence as blocking actionability gaps; they must not support an Actionability score of 2/2. Keep advisory gaps visible in TestPlanGaps.md without requesting source documents solely for those advisories.
- Defer to TestPlanGaps.md for unresolved items
- Only suggest changes that are directly traceable to source material

**Why these rules matter**: The reviewer's job is to assess completeness and consistency against source documents, not to fill gaps with assumptions. Inventing resolution paths or fabricating details creates false confidence - better to acknowledge gaps explicitly so they can be resolved with real documentation.

## What This Skill Does NOT Do

- Does NOT generate test plans (use `/test-plan-create`)
- Does NOT generate test cases (use `/test-plan-create-cases`)
- Does NOT modify the source strategy
- Does NOT submit anything to Jira
- Does NOT resolve GitHub PR comments (use `/test-plan-resolve-feedback <PR_URL>`)

$ARGUMENTS

---
name: test-plan-create
description: Generate a test plan from a strategy (RHAISTRAT or RHOAIENG issue), with optional ADR for extra technical depth. Use when starting test planning for a new RHOAI feature with a defined Jira strategy.
argument-hint: <JIRA_KEY> [ADR_FILE_PATH]
user-invocable: true
model: opus
allowedTools:
  - Read
  - Write
  - Bash
  - Glob
  - Skill
  - AskUserQuestion
---

# Test Plan Generator

Generate a complete test plan for a RHOAI feature based on a refined strategy, and optionally an ADR document for additional technical depth.

## Usage

```
/test-plan-create <JIRA_KEY> [ADR_FILE_PATH]
```

Examples:
- `/test-plan-create RHAISTRAT-400`
- `/test-plan-create RHOAIENG-48676`
- `/test-plan-create RHAISTRAT-400 /path/to/adr.pdf`

## Inputs

Parse `$ARGUMENTS` as:
1. Required Jira key: a `RHAISTRAT-*` strategy or `RHOAIENG-*` issue.
2. Optional local ADR path (Markdown, text, or PDF).

With no arguments, use a strategy created in this session by `/strat.create` or `/strat.refine` and
proceed to Step 1. If none is available, ask for the Jira key and optional local ADR path, ADR URL
(metadata only; never fetched), and optional snake_case feature-directory name. If omitted, derive the
directory name from the feature name.

## Process

### Step 0: Pre-flight Checks

#### 0.1 Python dependencies

Install the test-plan package so all scripts are importable from any directory:
```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv sync --extra dev)
```

If installation fails, inform the user and **STOP**; do not proceed.

#### 0.2 Jira Environment Variables

Verify that `JIRA_URL`, `JIRA_USER`, and `JIRA_TOKEN` are configured:

```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python -c "from scripts.jira_utils import require_env; [require_env(v) for v in ('JIRA_URL','JIRA_USER','JIRA_TOKEN')]")
```

If it exits non-zero, **STOP immediately**. Do not continue or use alternative sources (MCP, cache,
web, or any workaround). Report the error and tell the user to set the missing variables: `JIRA_URL`
(base URL), `JIRA_USER` (username/email), and `JIRA_TOKEN` (API token). Otherwise proceed to Step 0.3.

#### 0.3 Determine Output Directory

Keep test plan artifacts outside the skill repository. If `--output-dir` is present, use it as a
contributor override, set `FORCE_OUTPUT_DIR=true`, and skip validation. Otherwise read the saved
preference from `.claude/settings.json`, ask for a path with AskUserQuestion (empty uses the saved
path or `~/Code/opendatahub-test-plans/plans/`), and expand `~`.

Unless `FORCE_OUTPUT_DIR=true`, validate the target against the skill repository:
```bash
export CLAUDE_SKILL_DIR
force_flag=$([ "$FORCE_OUTPUT_DIR" = "true" ] && echo "--force" || echo "")
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/repo.py validate-local-path "$target_dir" $force_flag) || exit 1
```

Unless `--output-dir` was used, ask whether to save the path. On yes, atomically update only
`test-plan.output_dir` in `.claude/settings.json`, preserving other settings; on no, do not save.
Then create and enter the output directory:
```bash
mkdir -p "$target_dir"
cd "$target_dir"
echo "✓ Creating test plan artifacts in: $target_dir"
```

`save-snapshot` (Step 1.5) persists the output directory to
`<feature_dir>/.test-plan-output-dir.json` for discovery without environment variables.

### Step 1: Gather Information

1. **Strategy**: If a Jira key was provided, fetch it using the `fetch_issue.py` script. If auto-detected, read the local file from `artifacts/strat-tasks/` instead — do NOT fetch.

   **Fetching from Jira:**
   ```bash
   repo_root=$(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel)
   tmp_result=$(cd "$repo_root" && uv run python scripts/parse_strat.py new-strat-tmp) || exit 1
   strategy_file=$(echo "$tmp_result" | jq -r '.strategy_file')
   (cd "$repo_root" && \
    uv run python scripts/fetch_issue.py <JIRA_KEY> --output "$strategy_file")
   ```

   **Auto-detected from `artifacts/strat-tasks/<JIRA_KEY>.md`** (shared cache; also a Jira-outage fallback for other skills):
   ```bash
   resolve_result=$(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/parse_strat.py resolve-local "<JIRA_KEY>") || exit 1
   strategy_file=$(echo "$resolve_result" | jq -r '.strategy_file')
   ```

   - `components` is extracted deterministically in Step 1.5 (`parse_strat.py save-snapshot`).
2. **ADR** (if provided): Read the ADR file for additional technical detail (API endpoints, data models, implementation specifics).

### Step 1.5: Parse Strategy Sections and Snapshot the Strategy

Run the STRAT parser on the fetched strategy before snapshotting it:

```bash
repo_root=$(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel)
gate_result=$(cd "$repo_root" && uv run python scripts/parse_strat.py workflow-inputs "$strategy_file")
gate_exit=$?

if [ "$gate_exit" -ne 0 ]; then
  echo "workflow-inputs failed to parse the strategy; cannot proceed" >&2
  echo "$gate_result" >&2
  exit 1
fi

gate_status=$(echo "$gate_result" | jq -r '.status')
if [ "$gate_status" = "ok" ]; then
  ac_json=$(echo "$gate_result" | jq -c '.ac_json')
  nfr_json=$(echo "$gate_result" | jq -c 'if .nfr_json.found then .nfr_json else empty end')
  oos_json=$(echo "$gate_result" | jq -c 'if .oos_json.found then .oos_json else empty end')
  ac_count=$(echo "$gate_result" | jq -r '.ac_count')
  nfr_category_flags=()
  while IFS= read -r cat; do [ -n "$cat" ] && nfr_category_flags+=(--nfr-category "$cat"); done < <(echo "$gate_result" | jq -r '.nfr_categories[]? // empty')
fi

feature_name="<user-provided feature directory name from Inputs (Optional) if given, else snake_case derived from the strategy title>"
(cd "$repo_root" && uv run python scripts/validate.py feature-name "$feature_name") || exit 1
feature_dir="$(pwd)/$feature_name"
```

Snapshot to `$feature_dir/.source-strategy.md`; create the feature directory, move temp fetches, and
copy (never delete) the shared cache:

```bash
snapshot_result=$(cd "$repo_root" && uv run python scripts/parse_strat.py save-snapshot "$strategy_file" "$feature_dir") || exit 1
strategy_file=$(echo "$snapshot_result" | jq -r '.strategy_file')
components=$(echo "$snapshot_result" | jq -r '.components | join(",")')
```

If `$gate_status` is `no_acceptance_criteria` (no ACs or count 0), **STOP**:
1. Write a lowest-score review:
   ```bash
   (cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/frontmatter.py set \
       <absolute_path_to_output_dir>/<feature_name>/TestPlanReview.md \
       feature="<feature_name>" source_key=<JIRA_KEY> score=0 pass=false verdict=Rework \
       scores='{"specificity":0,"grounding":0,"scope_fidelity":0,"actionability":0,"consistency":0}' \
       auto_revised=false)
   ```
2. Write review body: `"Strategy has no acceptance criteria. Cannot generate AC-traced test plan."`
3. Stamp `test-plan-rubric-fail` on the Jira issue (non-blocking). Do NOT proceed to Step 2.

### Step 2: Analyze (Parallel Sub-Agents)

**Scope and traceability**: Generate e2e/system and UI plans only; Section 2.1 excludes unit,
integration, and component levels. Every Section 1.3 objective must cite a grounded AC/NFR. Every
meaningful in-scope entry in Sections 1.2, 2.3, 7.1–7.5, and 8 must end with `(Objective: #N)`
linking it to a grounded objective; do not guess `N`. A Section 7.1–7.5 category with no concrete
AC/NFR grounding is **Not Applicable** and needs no marker. Step 3.2 validates this deterministically.

The endpoint analyzer owns disclosure of every in-scope Section 1.2 item it omits from Section 1.3
solely because it lacks a backing AC. Pass that analyzer output through unchanged and collect its
required `## Gaps` output into `TestPlanGaps.md` at Step 3.5. The parent must not be responsible for
adding a concise entry in the analyzer `## Gaps` material passed to Step 3.5, inventing an objective,
or using a free-text matcher to infer further exclusions.

Invoke the three forked analyzer skills **in parallel** using the Skill tool. Each runs in isolation
and reads supplied strategy/ADR paths. Pass `<feature_name>/.source-strategy.md` and any ADR as
paths, never inline; pass the Step 1.5 JSON extractions as ground truth and do not re-derive them.

- **`test-plan.analyze.endpoints`**: Pass strategy, ADR, `ac_json`, `oos_json`, and `nfr_json`.
  Produce scope, grounded-objective, and e2e-surface findings for Sections 1 and 4.
- **`test-plan.analyze.risks`**: Pass strategy, ADR, `ac_json`, and `nfr_json`. Produce e2e/UI
  levels, types, priorities, mitigated risks, and NFR assessments for Sections 2, 7, and 8.
- **`test-plan.analyze.infra`**: Pass strategy and ADR. Produce environment, data, user,
  infrastructure, and tooling findings for Section 3.

After all three return, merge their findings into the template and collect their `## Gaps` sections
for Step 3.5. Do not add information absent from every sub-agent output.

**Evidence policy:** Apply one occurrence-level rule independently to Sections 3.1–3.3: a bare or
unresolved `TBD` is blocking; a genuinely unknown value is non-blocking only with an explicit resolution path
in the form `TBD — Resolution: {concrete action} from/with/by/before/after/using
{named source or timing}`. `derive` is valid when the named overlay or other source grounds it.
For test data, count examples only in explicit `Example`/`Sample`/`Fixture` labels or table columns,
or `e.g.,`/`for example` clauses; arbitrary backticks and broad words such as `token` are not enough.
Valid actionability may be `actionability == 2` with advisories; only `bare_tbd`/`missing_details`
block scoring.

### Step 3: Generate Files

1. Ensure `test_cases/` exists: `mkdir -p -- "$feature_dir/test_cases"`.
2. Resolve the strategy URL from configured `JIRA_URL` (falling back to `JIRA_BASE_URL`); never
   hardcode or infer a host:
   ```bash
   jira_url="${JIRA_URL:-$JIRA_BASE_URL}"
   strat_url="${jira_url%/}/browse/${JIRA_KEY}"
   ```
   Use this exact `strat_url` in the template and `README.md`.
3. Read `${CLAUDE_SKILL_DIR}/test-plan-template.md` and fill `TestPlan.md` exactly: preserve section
   order, use proper headings, do not write frontmatter manually, wrap prose/list items to 100
   characters, and apply Step 2 objective markers without marking excluded Section 1.2 items.
4. In Section 9.2 fill only Interface from Section 4; leave Test Cases and Coverage empty.
5. Generate `README.md` with the feature name/description, `strat_url`, optional ADR, TestPlan link,
   and the automated-test destination. The formatting rules also apply to these generated files.

### Step 3.1: Set Frontmatter

After generating `TestPlan.md`, set frontmatter with `frontmatter.py` via Bash; it validates the
metadata before writing. Set `SOURCE_TYPE` from the Jira key (`RHAISTRAT-*` → `strat`,
`RHOAIENG-*` → `issue`):
```bash
if [[ <JIRA_KEY> == RHAISTRAT-* ]]; then
    SOURCE_TYPE="strat"
elif [[ <JIRA_KEY> == RHOAIENG-* ]]; then
    SOURCE_TYPE="issue"
fi
```

Run Python from the test-plan repo (where `pyproject.toml` is), not the output directory, and use
absolute paths.

```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/frontmatter.py set <absolute_path_to_output_dir>/<feature_name>/TestPlan.md \
    feature="<feature_name>" \
    source_key=<JIRA_KEY> \
    source_type=$SOURCE_TYPE \
    status=Draft \
    author="<team_name>" \
    components="$components" \
    additional_docs="<comma-separated list of doc links, or []>")
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/version.py set <absolute_path_to_output_dir>/<feature_name>/TestPlan.md 1.0.0)
```

`components` comes from Step 1.5 (empty becomes `[]`); `additional_docs` contains the ADR and other
user-provided links (or `[]`). The scripts set `last_updated` and default `reviewers` to `[]`.
On error, fix values and retry; never write frontmatter by hand.

### Step 3.2: Validate Generated Test Plan

After frontmatter, run the deterministic checks below. Step 1.5 guarantees `$ac_count` and
`$nfr_category_flags` are available:

```bash
testplan="<absolute_path_to_output_dir>/<feature_name>/TestPlan.md"
feature_dir="<absolute_path_to_output_dir>/<feature_name>"
repo_root=$(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel)

team_list=$(cd "$repo_root" && uv run python scripts/get_component_test_dir.py --teams-only "$feature_dir") || {
    echo "ERROR: scripts/get_component_test_dir.py --teams-only failed — stopping." >&2
    echo "$team_list" >&2
    exit 1
}

(cd "$repo_root" && \
 scope_result=$(uv run python scripts/validate_test_scope.py "$testplan" \
     --include-teams="$team_list" --checks-dir=scripts/checks) && \
 (echo "$scope_result" | jq -e '.valid' >/dev/null || { echo "$scope_result" >&2; exit 1; }) && \
 uv run python scripts/validate.py ac-citations "$testplan" --ac-count "$ac_count" "${nfr_category_flags[@]}" && \
 uv run python scripts/validate.py ac-coverage "$testplan" --ac-count "$ac_count" && \
 uv run python scripts/validate.py structure "$testplan" && \
 uv run python scripts/validate.py category-prefixes "$testplan" && \
 uv run python scripts/validate.py interface-types "$testplan" && \
 uv run python scripts/validate.py infra-scope "$testplan")

citation_inputs=$(cd "$repo_root" && uv run python scripts/build_citation_inputs.py "$feature_dir" \
    --strategy-file "$strategy_file") || {
    echo "ERROR: scripts/build_citation_inputs.py failed — stopping." >&2
    echo "$citation_inputs" >&2
    exit 1
}
actionability_result=$(echo "$citation_inputs" | jq -c '.actionability_result')
echo "$citation_inputs" | jq -e '.scope_coverage_result.valid' >/dev/null || {
    echo "ERROR: scope coverage is incomplete; add `(Objective: #N)` markers and grounded objectives." >&2
    echo "$citation_inputs" >&2
    exit 1
}
```

If a check fails, fix `TestPlan.md` and retry once; if it fails again, **STOP** and report it.

### Step 3.5: Collect Gaps and Prompt for Additional Documents

Write each Step 2 sub-agent's full raw analysis verbatim to
`<feature_dir>/.analysis-endpoints.md`, `<feature_dir>/.analysis-risks.md`, and
`<feature_dir>/.analysis-infra.md`; the script extracts `## Gaps`, so do not hand-slice it.

Then run:

```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && \
 uv run python scripts/consolidate_gaps_and_stamp.py \
   --feature-name "<feature_name>" \
   --source-key <JIRA_KEY> \
   --source endpoints=<feature_dir>/.analysis-endpoints.md \
   --source risks=<feature_dir>/.analysis-risks.md \
   --source infra=<feature_dir>/.analysis-infra.md \
   --actionability-result "$actionability_result" \
   --last-updated "$(date -u +%F)" \
   --skip-cleanup \
   --out <feature_dir>/TestPlanGaps.md)
```

Success writes `TestPlanGaps.md` and prints `{"gap_count": int, "status": str, "next":
"proceed"|"prompt_user"}`. Never hand-count gaps, edit frontmatter, or run `check-interactive`;
staging files remain on failure for debugging.

The payload's `advisory_gaps` are rendered in an Advisory Actionability Gaps section for visibility
only: they do not change `gap_count`, status, or the document menu. Only consolidated analyzer
groups drive that menu; blocking actionability fields still reach review. Reclassify only matching
version/build-only or test-data-format/example-only analyzer concerns; count unrelated concerns and
keep reclassified findings visible. Never request documents solely for advisories.

If `next` is `proceed`, go to Step 3.6. If it is `prompt_user`, use AskUserQuestion for the
consolidated analyzer groups and show advisories only as informational follow-ups:

1. **Provide documents** — paste file paths to resolve gaps
2. **Proceed to review** — continue as-is
3. **Proceed + generate test cases** — continue and auto-run `/test-plan-create-cases`

**If option 1:** Read documents, rerun only relevant Step 2 sub-agents, and update the test plan. Then
recompute gate inputs against the edited plan before collecting gaps, so stale actionability evidence
is not reused:
```bash
citation_inputs=$(cd "$repo_root" && uv run python scripts/build_citation_inputs.py "$feature_dir" \
  --strategy-file "$strategy_file") || { echo "$citation_inputs"; exit 1; }
actionability_result=$(echo "$citation_inputs" | jq -c '.actionability_result')
```
Rerun the same `consolidate_gaps_and_stamp.py` command (including `--skip-cleanup`) with fresh
`actionability_result`, then follow the new `next`. **If option 2:** proceed to Step 3.6; **option 3**
also invokes `/test-plan-create-cases` with the feature directory after Step 4.

### Step 3.6: Stamp Jira label — test plan created

Add `test-plan-auto-created` to the source Jira issue to mark the generated plan for org-pulse tracking.

Read `source_key` from `<feature_name>/TestPlan.md` frontmatter before stamping:
```bash
source_key=$(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && uv run python scripts/frontmatter.py read <absolute_path_to_output_dir>/<feature_name>/TestPlan.md source_key)
```

Then add the label with `add_jira_labels.py`:
```bash
(cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && \
 uv run python scripts/add_jira_labels.py "$source_key" test-plan-auto-created)
```

### Step 4: Review, Score, and Improve

After the gaps flow, invoke the internal **`test-plan.review`** skill with the feature directory. It
applies the 10-point rubric (Specificity, Grounding, Scope Fidelity, Actionability, Consistency;
0–2 each), may auto-revise internally for up to 2 cycles, and writes
`<feature_name>/TestPlanReview.md` with scores and feedback. Full criteria live in `test-plan.review`.

**Refresh TestPlanGaps.md** after the review returns (the revision loop may have resolved blocking
gaps or introduced new advisories). Recompute `actionability_result` from the final `TestPlan.md`
and rerun `consolidate_gaps_and_stamp.py` with the same flags used in Step 3.5:

```bash
repo_root=$(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel)
citation_inputs=$(cd "$repo_root" && uv run python scripts/build_citation_inputs.py <feature_dir> \
  --strategy-file "$strategy_file") || { echo "$citation_inputs"; exit 1; }
actionability_result=$(echo "$citation_inputs" | jq -c '.actionability_result')

(cd "$repo_root" && \
 uv run python scripts/consolidate_gaps_and_stamp.py \
   --feature-name "<feature_name>" \
   --source-key <JIRA_KEY> \
   --source endpoints=<feature_dir>/.analysis-endpoints.md \
   --source risks=<feature_dir>/.analysis-risks.md \
   --source infra=<feature_dir>/.analysis-infra.md \
   --actionability-result "$actionability_result" \
   --last-updated "$(date -u +%F)" \
   --skip-cleanup \
   --out <feature_dir>/TestPlanGaps.md)
```

**Handle the review output:**

1. Read the verdict from `<feature_name>/TestPlanReview.md` frontmatter.
2. Apply only clearly correct improvements:
   - Consistency fixes, such as Section 4 interfaces missing from Section 9.2.
   - Feature-specific priority definitions when the strategy supplies the language.
   - **TBD/actionability:** use the Evidence policy above independently for each occurrence; never
     invent a resolution path. Repair only blocking `bare_tbd`/`missing_details` when sources provide
     the facts. Missing/vague versions and incomplete data format/examples are advisory: keep them in
     `TestPlanGaps.md` and do not revise or request documents solely for them. Missing Section 3.1 or
     unusable RBAC remains blocking. A plan may claim Actionability 2/2 only with no blocking gaps.
   - Add content only when directly traceable to strategy, ADR, API/design docs, or `additional_docs`.

   Use the Edit tool for applied auto-fixes.
3. Show the final score/verdict, auto-fixes, and remaining `TestPlanGaps.md` gaps.
4. For **Rework**, request source documents before test cases when the remaining failure is a
   blocking grounding or operational gap; advisory actionability gaps alone do not require them.

### Step 4.5: Stamp rubric verdict label

From the test-plan repo, use `frontmatter.py read` with absolute paths to get `verdict` and
`auto_revised` from `TestPlanReview.md` and `source_key` from `TestPlan.md`; do not parse YAML by
hand. Add the corresponding Jira label:

| Verdict | Label |
|---------|-------|
| `Ready` | `test-plan-rubric-pass` |
| `Revise` | `test-plan-rubric-revise` |
| `Rework` | `test-plan-rubric-fail` |

For any other verdict, warn and skip. If `auto_revised=true`, also add
`test-plan-auto-revised`.

```bash
repo_root=$(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel)
source_key=$(cd "$repo_root" && \
    uv run python scripts/frontmatter.py read <absolute_path_to_output_dir>/<feature_name>/TestPlan.md source_key)
verdict=$(cd "$repo_root" && \
    uv run python scripts/frontmatter.py read <absolute_path_to_output_dir>/<feature_name>/TestPlanReview.md verdict)
auto_revised=$(cd "$repo_root" && \
    uv run python scripts/frontmatter.py read <absolute_path_to_output_dir>/<feature_name>/TestPlanReview.md auto_revised)

if [ "$auto_revised" = "true" ]; then
    (cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && \
     uv run python scripts/add_jira_labels.py "$source_key" --verdict "$verdict" test-plan-auto-revised)
else
    (cd $(git -C ${CLAUDE_SKILL_DIR} rev-parse --show-toplevel) && \
     uv run python scripts/add_jira_labels.py "$source_key" --verdict "$verdict")
fi
```

Label stamping is **non-blocking**: on failure, warn and continue without retrying or halting.

### What this skill does NOT do

- **Sources/feedback:** Fetch only the requested strategy or issue; never fetch child stories. Read
  ADRs only from supplied local paths (URLs are metadata); use `/test-plan-resolve-feedback` for
  GitHub PR comments.
- **Test cases/ownership:** Do not create `TC-*.md` files or executable tests. Keep Sections 5.1, 6,
  and 9.1 as placeholders; Section 5.2 is the category contract. `/test-plan-create-cases` owns
  case files, Sections 5.1, 6.1–6.2, Section 9.1, and Section 9.2 Test Cases; this skill owns only
  Section 9.2 Interface and Section 9.3's change log. Downstream tooling fills Coverage.
- **Scope/analysis:** Section 2.1 permits only e2e/system and UI. Cover every AC and grounded NFR
  with valid citations; never invent objectives, scope, NFR analysis, risks, or mitigations.

$ARGUMENTS

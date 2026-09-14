# Test Scorer Calibration Files

## Purpose

These files train the **test-plan.score.test-function** scorer agent to distinguish
high-quality tests (9-10/10) from low-quality tests (2/10).

**Key distinction:**

- **Tiger Team rules** (`~/Code/Red-Hat-Quality-Tiger-Team/.claude/rules/`) → Train the
  CODE GENERATOR (how to write tests)
- **Calibration files** (this directory) → Train the SCORER (what quality looks like)

## Layout

Plugin default is pytest E2E (`opendatahub-tests`). Load order is **core → ui → teams**.

```text
calibration/core/    # pytest good/poor only (required)
calibration/ui/      # Cypress now; Playwright later (optional overlay)
calibration/<team>/  # optional extras (same team names as COMPONENT_TEST_DIR_MAP)
```

- **`core/`** — pytest pairs only. Other frameworks do not belong here.
- **`ui/`** — Cypress (and later Playwright). Not a COMPONENT team name.
- **`<team>/`** — Go, generic TypeScript, or other team-specific extras. Adding a pair is
  a new file; no `SKILL.md` edit.

**Files in core:**

- `good-pytest-test.py` / `poor-pytest-test.py`

**Files in ui:**

- `good-cypress-test.cy.ts` / `poor-cypress-test.cy.ts`
- Playwright pairs can be added here later (do not invent them until they exist)

## Framework filename token (`--framework`)

`load_calibration.py --framework` matches a **whole token** in the filename (split on
non-alphanumerics, case-insensitive). The token must be the `get_framework.py` value:
`pytest`, `cypress`, `playwright`, etc.

Examples:

- `good-pytest-test.py` / `poor-pytest-test.py` → `--framework pytest`
- `good-cypress-test.cy.ts` → `--framework cypress`
- Future Playwright pair: `good-playwright-test.spec.ts` → `--framework playwright`
  (not a generic `good-ui-test.spec.ts`)

If no file matches that token, function calibration is empty (score without those
examples). `core/` must still be non-empty (pytest pair).

## Hybrid Approach

### Frameworks WITH Tiger Team Rules

For Cypress (in `ui/`) and for Go/TypeScript (via team dirs when added), calibration
files:

- Reference Tiger Team rules for patterns (avoid duplication)
- Focus on demonstrating QUALITY LEVEL (9/10 vs 2/10)
- Show complete examples with explicit rubric scoring

### Frameworks WITHOUT Tiger Team Rules

For pytest (no Tiger Team rules exist yet), calibration files in `core/` are
**standalone**:

- Complete pattern guidance
- Quality scoring demonstration

## Calibration File Structure

Each file has a header with:

```
// SCORER CALIBRATION: [HIGH|LOW] QUALITY test (should score X/10)
//
// Purpose: Trains scorer to recognize [excellent|poor] [framework] test quality.
//          For PATTERN guidance, see Tiger Team rules at: [path] (if available)
//
// Rubric Scores (5 criteria, 0-2 each, total 10):
// ✅/❌ Coverage: X/2 - [explanation]
// ✅/❌ Assertions: X/2 - [explanation]
// ✅/❌ Conventions: X/2 - [explanation]
// ✅/❌ Test Data: X/2 - [explanation]
// ✅/❌ Code Quality: X/2 - [explanation]
//
// This example demonstrates QUALITY LEVEL (X/10), not just patterns.
```

## Scoring Rubric

> The authoritative rubric lives in `../prompts/score-test-function.md`. Keep the two in sync —
> the summaries below must reflect the same criteria.

### Coverage (0-2 points)

- **2**: All TC requirements implemented (preconditions, steps, assertions). Mandatory
  active-feature preconditions gated with `pytest.fail`, not `skip`
- **1**: Missing 1-2 items, or has TODOs for specified requirements
- **0**: Missing major sections, or mostly TODOs

### Assertions (0-2 points)

- **2**: Specific, feature-specific assertions with clear messages. Tight, not loose: exact type
  checks over broad ABCs (`float`, not `numbers.Real`, which also accepts `int`/`bool`); finiteness
  checks (reject `NaN`/`inf`); non-empty collection checked before indexing (`choices[0]`); iterates
  **all** candidates (containers/files/matches), not just the first
- **1**: Some generic assertions, missing messages, or a loose/probabilistic assertion
- **0**: Mostly generic "false-green" assertions, probabilistic assertions on model output, or
  expected results have TODOs

### Conventions (0-2 points)

- **2**: Follows framework patterns and repo conventions; registered markers, correct tier,
  `skip_on_disconnected` on live-external tests
- **1**: Mostly follows with 1-2 deviations
- **0**: Uses patterns not in conventions, invents/unregistered markers, negative tests in wrong tier

### Test Data (0-2 points)

- **2**: Uses exact values from TC test data
- **1**: Reasonable values but not from TC
- **0**: Placeholders ("test123") or wrong formats

### Code Quality (0-2 points)

- **2**: No TODOs for specified requirements, clean implementation, bounded loops, safe helpers
- **1**: Some TODOs for unclear items, minor issues
- **0**: Many TODOs for TC-specified items, fabricated helpers, unbounded loops, or unsafe helper
  code (shell injection, substring-vs-exact, unhandled enum)

## Verdict Mapping

| Score | Verdict | Action |
|-------|---------|--------|
| 9-10  | Ready   | Accept |
| 7-8   | Good    | Accept |
| 4-6   | Revise  | Auto-revision |
| 0-3   | Rework  | Flag for manual review |

## When to Update

**Add new calibration files when:**

- Adding pytest examples: drop files in `core/`
- Adding Cypress or Playwright examples: drop files in `ui/`
- Adding Go, TypeScript, or other extras: drop files in the relevant `calibration/<team>/`

**Update existing files when:**

- Rubric criteria change
- Tiger Team rules significantly evolve
- Quality expectations shift

## Relationship to Tiger Team

**Current state (2026-04-20):**

- Tiger Team has: TypeScript, Go, Cypress rules (pattern guidance)
- Tiger Team missing: pytest rules
- Calibration complements Tiger Team by adding quality scoring

**If Tiger Team adds quality scoring in the future:**

- We can further reduce duplication
- Calibration can become even leaner (just reference Tiger Team scores)
- But scoring will likely remain separate (different purpose)

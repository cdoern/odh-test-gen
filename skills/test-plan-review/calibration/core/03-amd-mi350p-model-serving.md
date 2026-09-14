# Calibration Example 3: amd_mi350p_model_serving/TestPlan.md

**Source**: `amd_mi350p_model_serving/TestPlan.md` (RHAISTRAT-2528)
**Test plan version**: Pre-test-case generation (Section 5 unpopulated), post-revision (Cycle 1 applied)
**Note**: This is the calibration set's first **Ready**-verdict anchor under the actionability gate. Examples 1 and 2 both land below Ready — this example shows what a plan that
clears `actionability == 2` looks like, including that Ready does not require a perfect 10/10.

## Score Table

| Criterion | Score | Evidence | Rationale |
|-----------|-------|----------|-----------|
| Specificity | 2 | Section 8 risks name specific dependencies (RHOAIENG-66855, CVE-2026-49121, CDNA 4 vs CDNA 3 kernel differences). Section 2.3 priorities reference MI350P-specific scenarios (gfx950 GPU recognition, graceful degradation). | Swap test: "AMD MI350P gfx950 GPU device plugin recognition" cannot be pasted into a test plan for an unrelated feature. Language is tied to this specific hardware generation, not generic "GPU support" boilerplate. |
| Grounding | 1 | 9/10 Section 4 entries trace directly to strategy source material (`/v1/completions`, InferenceService, HardwareProfile, vllm-rocm-runtime-template, etc.). One entry, "Gateway API HTTPRoute," is extrapolated — the strategy names "llm-d EPP" but does not explicitly call out Gateway API or HTTPRoute as a distinct component. | Mostly grounded with one clear extrapolation, not a fabrication. Losing a point here (rather than 2) is the correct call — the inference is reasonable but not source-traceable, matching the same standard applied in Examples 1 and 2. |
| Scope Fidelity | 2 | All 6 strategy HLRs mapped to test objectives. All acceptance criteria covered. Section 7.1 (Disconnected/Air-Gapped) correctly marked N/A with justification, since the strategy's NFRs cover only Backwards Compatibility, Security, and Performance. | No orphan objectives, no scope creep, and the N/A marking is itself evidence of scope discipline rather than an omission. |
| Actionability | 2 | Section 3.1 pins concrete versions/builds where known (RHOAI 2.25, ROCm 7.14 minimum, vLLM 0.24.0+rhaiv.2, exact GA image reference); its RHOAI 3.3+ compatibility range is advisory. Its one unknown OCP version is recorded as `TBD — Resolution: confirm the compatible OCP version with the AMD GPU device plugin owner before environment provisioning`. Section 3.3 provides a structured 4-row table of user roles with named RBAC bindings (cluster-admin, admin, edit, ServiceAccount) and per-role purpose. | A platform engineer could start provisioning immediately: versions are pinned or have a concrete, explicit resolution path, with the compatibility range retained as a non-blocking advisory; roles have concrete access levels rather than personas alone. This is the bar Example 1 fell short of because of unresolved model-server and permission TBDs, not its advisory version omissions. |
| Consistency | 2 | Section 9.2 lists exactly the same 10 components as Section 4. Section 7.1 N/A no longer contradicts Section 1.2 scope (resolved in Cycle 1 revision). All seven cross-checks pass, including the pre-test-case E2E coverage placeholder check. | No mismatches. The revision history documents exactly what changed to resolve the prior Section 7.1/1.2 contradiction, which is itself traceable evidence for this score. |

**Total: 9/10 — Verdict: Ready**

## Key Observations

- This is the calibration set's Ready anchor: actionability == 2 AND total >= 8 AND no criterion
  scored 0. It demonstrates that Ready does not require a flawless plan — grounding at 1/2 is an
  accepted, well-justified deduction, not a blocker.
- Contrast with Example 1: both plans have identical Specificity/Scope Fidelity/Consistency
  patterns, but Example 1's actionability=1 because its model server is a bare "TBD" with no
  explicit resolution path and its permissions are unresolved. Its vague version values alone
  would be advisory; this plan's actionability=2 has versions pinned or recorded with a concrete
  resolution path and a concrete RBAC table instead of personas. An unknown required value
  supports `actionability == 2` only in the form
  `TBD — Resolution: {concrete action} from/with/by/before/after/using {named source or timing}`;
  `derive` is also valid when the named source grounds the derivation. The rule is applied to each
  TBD occurrence across infrastructure, test data, and RBAC.
- This plan reached Ready only after one revision cycle (before_score=7 -> score=9). The jump
  isn't actionability alone: before_scores were specificity=2, grounding=2, scope_fidelity=1,
  actionability=1, consistency=1. Cycle 1 touched three criteria — Scope Fidelity (marked Section
  7.1 N/A with justification), Actionability (added the Section 3.3 RBAC table), and Consistency
  (resolved the Section 7.1/1.2 contradiction that N/A marking created) — each +1, while Grounding
  independently dropped 2 -> 1 between assessments (net +2 overall: -1+1+1+1). The actionability
  change specifically is the kind of concrete edit that moves a plan from "some sections concrete"
  (score 1) to "a tester
  could begin environment setup immediately" (score 2).

# Calibration Example 2: kagenti_agent_templates_1/TestPlan.md

**Source**: `kagenti_agent_templates_1/TestPlan.md` (RHAISTRAT-1290)
**Test plan version**: Without test cases (Sections 5 and 9.1 unpopulated; 9.2 lists Section 4 without test-case mappings), no YAML frontmatter
**Note**: This example predates Section 6 (E2E Scenarios) and Section 7 (NFR Assessment). It demonstrates the original four-cross-check consistency model. Modern test plans should evaluate seven cross-checks (scope subset, test levels, priorities, 9.2, NFRs, 6.2, ac_citations_result.valid).

## Score Table

| Criterion | Score | Evidence | Rationale |
|-----------|-------|----------|-----------|
| Specificity | 2 | P0 references kagenti deployment artifacts specifically: "labels, well-known.json, agentRuntime; agents deploy successfully on OpenShift AI; AgentCards are discoverable." Risks name kagenti runtime breaking changes, model server auth variation, well-known.json schema absence, GenAI Studio export alignment. | Swap test: "Kagenti runtime behavior changes break template-generated agentRuntime configurations" does not apply to any other feature. Risk about "No specification for well-known.json schema" is specific to this feature's AgentCard serving concern. |
| Grounding | 1 | Section 4 uses "Components Under Test" rather than API endpoints, which is a better fit for this feature type. Entries (Containerfile, well-known.json, agentRuntime CR, evaluate.py, MLflow, GenAI Studio export) align with strategy themes. However, "GenAI Studio code export" as a CLI/UI Component in Section 4 goes beyond what the strategy explicitly scopes — the strategy mentions export integration but doesn't specify it as a testable component interface. MLflow versions are not sourced. | Similar to Example 1: concepts are grounded but specific interface characterizations extrapolate beyond the strategy text. The GenAI Studio inclusion in Section 4 is borderline scope creep for grounding purposes. |
| Scope Fidelity | 2 | All strategy deliverables mapped to objectives. Out-of-scope list is more specific than Example 1 (adds "post-deployment monitoring, scaling, performance under load", "multi-cluster deployment", "custom template creation"). Section 4 includes GenAI Studio export which IS in-scope per the strategy. | No orphans in either direction. Each in-scope item has a corresponding objective. Out-of-scope items do not appear in Section 4. |
| Actionability | 0 | Section 3.1 contains bare/unresolved "TBD" values for the OpenShift AI and kagenti operator versions, and the plan supplies no usable test-data format/examples or concrete RBAC evidence. | The score is 0 because required environment values are explicitly bare TBDs and the operational evidence is unusable, not merely because versions or data are vague. A platform engineer cannot begin without resolving those blocking gaps. |
| Consistency | 1 | Section 4 has 8 entries but Section 9.2 lists them without any test case mappings (placeholder state). Test levels in 2.1 (Template Integration, Container Build, Deployment, API Integration, Functional, Documentation) are reasonable but "Documentation Testing" as a test level has no corresponding interface type in Section 4. Section 5 is entirely unpopulated ("Note: Test cases have not been generated yet"). | Section 9.2 lists all Section 4 components (passes that check), but the empty test case columns mean coverage cannot be verified. "Documentation Testing" as a test level has no counterpart in Section 4. Minor but real inconsistency. The placeholder state of Sections 5/9.1 is expected for a pre-TC-generation plan, so partial credit. |

**Total: 6/10 — Verdict: Rework**

## Key Observations

- Scores 0 on Actionability due to pervasive bare/unresolved "TBD" values and no concrete environment details — this is the primary blocking failure. Missing or vague version/data evidence would be advisory only when the required Section 3.1 and RBAC evidence was otherwise usable.
- Strong specificity (same feature, similar quality of feature-specific language)
- No YAML frontmatter — would fail the frontmatter check entirely (structural issue separate from rubric)
- The plan is in a pre-test-case state, which naturally weakens consistency but does not excuse the actionability gaps
- Grounding is comparable to Example 1 (reasonable inferences, not fabrications)
- A Rework verdict here is correct: the actionability zero means the plan needs significant environment detail before it's useful, regardless of other scores

## Comparison with Example 1

| Criterion | Example 1 | Example 2 | Delta | Explanation |
|-----------|-----------|-----------|-------|-------------|
| Specificity | 2 | 2 | 0 | Both handle feature-specific language well |
| Grounding | 1 | 1 | 0 | Same source material, similar extrapolation patterns |
| Scope Fidelity | 2 | 2 | 0 | Both align well with strategy |
| Actionability | 1 | 0 | -1 | Example 1 has concrete tools but unresolved model-server/permission TBDs; Example 2 has bare "TBD" values and no usable operational evidence |
| Consistency | 2 | 1 | -1 | Example 1 has populated TCs and coverage; Example 2 has placeholders and a test-level mismatch |
| **Total** | **8** | **6** | **-2** | Example 1 (actionability=1) and Example 2 (actionability=0) both fail to reach Ready; Example 1 lands in Revise, Example 2 in Rework |

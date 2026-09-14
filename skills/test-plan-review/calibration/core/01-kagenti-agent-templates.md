# Calibration Example 1: kagenti_agent_templates/TestPlan.md

**Source**: `kagenti_agent_templates/TestPlan.md` (RHAISTRAT-1290)
**Test plan version**: With test cases generated (36 TCs, Sections 5/10 populated)
**Note**: This example predates Section 6 (E2E Scenarios) and Section 7 (NFR Assessment). It demonstrates the original four-cross-check consistency model. Modern test plans should evaluate seven cross-checks (scope subset, test levels, priorities, 9.2, NFRs, 6.2, ac_citations_result.valid).

## Score Table

| Criterion | Score | Evidence | Rationale |
|-----------|-------|----------|-----------|
| Specificity | 2 | P0 definition names kagenti OCI labels, agentRuntime CR rejection, AgentCard discovery failure. Risks name kagenti runtime, GenAI Studio export format, well-known.json schema evolution. | Swap test: "kagenti runtime availability" cannot be pasted into a test plan for a database migration feature. Priority definitions describe deployment-specific failure scenarios, not generic "core functionality" language. |
| Grounding | 1 | Section 4 entries (well-known.json, agentRuntime CR, OCI labels, evaluate.py, MLflow) match strategy themes. However, specific endpoint paths are not in the strategy — "well-known.json" is inferred from the concept of AgentCard serving rather than an explicit API path. MLflow version "2.x" is assumed, not sourced. | Mostly grounded but some extrapolation. The strategy describes the *concepts* (AgentCard, OCI labels, evaluation) but not specific REST paths or tool versions. These are reasonable inferences rather than fabrications, but they are not traceable to a specific sentence. |
| Scope Fidelity | 2 | Every in-scope item maps to at least one test objective. Out-of-scope items (kagenti operator internals, model server runtime, GenAI Studio non-export features) are absent from Section 4. No scope creep. | Strategy deliverables: OCI labels (Obj 1), well-known.json (Obj 2), agentRuntime CR (Obj 3), model server config (Obj 4), evaluation stubs (Obj 5-6), end-to-end lifecycle (Obj 7). All covered. |
| Actionability | 1 | Specific tools named (podman 4.x+, oc 4.16+, MLflow 2.x, Python 3.11+). Test users have personas with named roles (Alex=developer, Paula=platform engineer). OpenShift version is "4.16+" (advisory range), RHOAI version is not specified, and "latest stable release as of test execution" is vague. Separately, the model server is "TBD" and GenAI Studio access has "permissions TBD" with no resolution path, leaving material operational blockers. | A platform engineer could start provisioning but would ask: "Which model server?" and "What are GenAI Studio permissions?" The unresolved required TBDs, not the advisory version omissions alone, keep this below Actionability 2/2. |
| Consistency | 2 | Section 4 has 7 entries; Section 9.2 lists all 7 with mapped test cases. Test levels (Functional, Integration, E2E, Compliance, API) match the interface types in Section 4 (Config, REST, Method, UI). Priority assignments in Section 4 match the definitions in Section 2.3 (P0 = deployment/discovery blockers, P1 = workflow blockers). | All four cross-checks pass (seven in modern rubric, but this plan predates Section 6/7). No orphan endpoints, no mismatched priorities. |

**Total: 8/10 — Verdict: Revise**

## Key Observations

- This is a well-structured test plan with strong specificity and scope fidelity
- The main weakness is grounding: several technical details are reasonable inferences rather than verbatim strategy content
- Actionability scores 1/2 (below the gate for Ready). Although the total qualifies (8/10), the actionability==2 requirement means this plan receives a **Revise** verdict — it needs clarification on the unresolved model-server and GenAI Studio permission TBDs before proceeding to test case generation. The missing/vague version values are advisory and would not alone require revision.
- The test plan was generated with test cases already populated, which strengthens the consistency score (Section 9.2 has mapped TCs)

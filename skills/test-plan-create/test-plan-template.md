# {feature_name} Test Plan
**{team_name}** – **{testing_focus}**

**Strategy**: [{source_key}]({strat_url})

---

## 1. Executive Summary

### 1.1 Purpose
{1-2 paragraphs describing what is being tested and why, derived from the strategy and its business need}

### 1.2 Scope

#### In Scope ({team_name} Responsibilities)
{Bulleted list derived from the strategy and its business need. Every meaningful in-scope entry
must end with the Section 1.3 objective it implements: `(Objective: #N)`. For example:
- Verify successful login through the dashboard (Objective: #1)}

#### Out of Scope (Other Teams)
{Bulleted list of explicitly excluded areas from the strategy and its business need}

### 1.3 Test Objectives
{Numbered list (1. 2. 3. ...) — at least one objective per STRAT
acceptance criterion. Each objective cites the AC or NFR it validates
using the machine-checkable form (AC: #N — short description) or
(NFR: category — short description). For example:
1. Verify successful login with valid credentials (AC: #1 — user can authenticate)

---

## 2. Test Strategy

### 2.1 Test Levels
{Only e2e/system and UI test levels. Examples:}
- **E2E System Testing** — End-to-end workflows exercising the deployed
  system through its external interfaces (API, CLI, CRD)
- **UI Testing** — Dashboard interactions, form validation, navigation
  flows verified through the browser

### 2.2 Test Types
- **Positive Testing** — Valid inputs, expected workflows
- **Negative Testing** — Invalid inputs, error conditions, unauthorized access, edge cases

### 2.3 Test Priorities
- **P0 (Critical)** - {description of what qualifies as P0 for this feature} (Objective: #N)
- **P1 (High)** - {description of what qualifies as P1} (Objective: #N)
- **P2 (Medium)** - {description of what qualifies as P2} (Objective: #N)

---

## 3. Test Environment

### 3.1 Infrastructure & Configuration
{Cluster-side requirements to execute tests: OpenShift version, RHOAI version,
operator versions, databases, cluster config, env vars on test harness,
credentials. Does not include developer tooling (pip, podman, Ollama,
docker-compose) or SUT configuration (CRD field values, ConfigMap contents)
— those belong in test case preconditions.}

{Concrete OpenShift and RHOAI versions/builds are preferred. If either is missing or vague,
leave it as an advisory gap rather than inventing a value. For a genuinely unavailable value,
use exactly `TBD — Resolution: {concrete action} from/with/by/before/after/using {named source
or timing}`. A bare or unresolved `TBD` is a blocking gap.}

### 3.2 Test Data Requirements
{What test data types are needed — describe shape and constraints, not
full manifests. Include concrete `format:` values and examples where known; strings,
identifiers, manifests, and URIs are valid evidence. An example must be in an explicit
`Example:`, `Sample:`, or `Fixture:` label, an Example/Sample/Fixture table column, or an
`e.g.,`/`for example` clause. Arbitrary inline backticks and broad words such as `token` do not
by themselves establish a format or example. Actual fixtures belong in test automation. Missing
or incomplete format/examples remain visible as advisory gaps. A bare or unresolved `TBD` for a
required data value remains blocking; do not use it to disguise an incomplete example.}

### 3.3 Test Users
{Service accounts, admin users, anonymous users needed for testing. State concrete roles,
permissions, and resources; missing or unusable RBAC evidence is blocking.}

{Apply the same unresolved-TBD rule independently to Sections 3.1, 3.2, and 3.3: every bare or
unresolved `TBD` is blocking. A genuinely unknown value is non-blocking only as
`TBD — Resolution: {concrete action} from/with/by/before/after/using {named source or timing}`;
`derive` is a valid action when the named source grounds the derivation (for example, named
overlay RBAC requirements).}

### 3.4 Test Tools
{Tools QE uses to run and observe tests: oc/kubectl, curl/httpie, pytest,
test frameworks, log viewers. Developer tooling (pip, podman, Ollama,
docker-compose) is not test infrastructure.}

---

## 4. Interfaces Under Test

{Interfaces the test actively sends requests to or interacts with during
execution. Does not include config files, environment variables, or CRD
fields consumed during setup — those belong in test case preconditions.}

| Interface | Type | Purpose |
|-----------|------|---------|
| {interface} | {REST/gRPC/UI/CLI/CRD} | {purpose} |

---

## 5. Test Cases

> **Note**: Test cases have not been generated yet. To be filled later in the process.

**Test Cases Directory**: [test_cases/](test_cases/)
**Complete Test Case Index**: [test_cases/INDEX.md](test_cases/INDEX.md)

### 5.1 Test Case Organization

> **Note**: To be filled later in the process.

| Category | Test Cases | Priority Distribution |
|----------|------------|----------------------|
| | | |

### 5.2 Test Case Naming Convention

Test cases follow the naming pattern: `TC-<CATEGORY>-<NUMBER>`

Only the following category prefixes are allowed — feature areas go in the
test case name after the prefix, not as a separate category:

| Prefix | Meaning |
|--------|---------|
| TC-E2E | End-to-end user journey flows |
| TC-UI | Browser-based UI interaction flows |
| TC-NEG | Negative and error path journeys |
| TC-NFR | Non-functional requirement validation (performance, disconnected, RBAC) |
| TC-UPG | Upgrade path validation |

Select only the categories relevant to the feature under test.

---

## 6. E2E Test Scenarios

End-to-end scenarios that validate the user journeys defined in the
strategy. Coverage rows may reference one or more `TC-E2E-*` or `TC-UI-*`
test cases generated by `/test-plan-create-cases`.

> **Requirement**: Once populated, the matrix must include every non-pending interface from
> Section 4, and each populated row must contain at least one `TC-E2E-*` or `TC-UI-*` reference.
> The matrix remains empty until `/test-plan-create-cases` runs.

### 6.1 Scenario Summary

> **Note**: E2E scenarios have not been generated yet. To be filled later in the process.

| ID | Scenario | Interfaces Covered | Priority |
|----|----------|-------------------|----------|
| | | | |

### 6.2 E2E Coverage Matrix

> **Note**: To be filled later in the process.

| Interface (from Section 4) | E2E Scenarios |
|----------------------------|---------------|
| | |

---

## 7. Non-Functional Requirements

Each category below must be explicitly addressed. If a category
does not apply to this feature, state **Not Applicable** with a
brief justification. Concrete testing considerations must end with
`(Objective: #N)`; a **Not Applicable** statement has no grounded
AC/NFR to cite and does not need the marker.

### 7.1 Disconnected/Air-Gapped

{Testing considerations for disconnected or air-gapped deployments, each ending with
`(Objective: #N)`.
Address: image mirroring, offline operator installation, registry
access, network-restricted environments, catalog source
configuration.}

{If not applicable: "**Not Applicable** — this feature does not
interact with external registries, image pulls, or
network-dependent resources at runtime." No `(Objective: #N)` needed.}

### 7.2 Upgrade/Migration

{Testing considerations for upgrades and migrations, each ending with `(Objective: #N)`. Address:
backwards compatibility with previous RHOAI versions, operator
upgrade paths, data migration, CRD schema changes, rollback
scenarios.}

{If not applicable: "**Not Applicable** — this feature introduces
no persistent state, CRD changes, or version-dependent behavior." No `(Objective: #N)` needed.}

### 7.3 Performance/Scalability

{Testing considerations for performance and scalability, each ending with `(Objective: #N)`. Address:
response time under load, resource consumption, behavior with
large datasets, concurrent user limits, degradation patterns.}

{If not applicable: "**Not Applicable** — this feature has no
user-facing latency path or data-volume-dependent behavior." No `(Objective: #N)` needed.}

### 7.4 RBAC/Authorization

{Testing considerations for role-based access control, each ending with `(Objective: #N)`. Address:
permission boundaries per role, multi-tenant isolation, privilege
escalation prevention, service account permissions, anonymous
access restrictions.}

{If not applicable: "**Not Applicable** — this feature does not
expose any endpoints or resources that require authorization
checks." No `(Objective: #N)` needed.}

### 7.5 Security

{Testing considerations for authentication, transport security, and
data protection — distinct from 7.4's access-control concerns.
Each consideration must end with `(Objective: #N)`.
Address: authentication/token handling, transport encryption (TLS),
credential and secrets storage, audit logging.}

{If not applicable: "**Not Applicable** — this feature does not
involve authentication mechanisms, token or session handling,
transport encryption (TLS), credential or secrets storage, or
audit logging." No `(Objective: #N)` needed.}

---

## 8. Risks and Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| {risk} | {High/Medium/Low} | {High/Medium/Low} | {mitigation strategy} (Objective: #N) |

---

## 9. Appendix

### 9.1 Test Case Summary

> **Note**: To be filled later in the process.

| Category | Total | P0 | P1 | P2 |
|----------|-------|----|----|-----|
| | | | | |

### 9.2 Interface Coverage

{Fill in the Interface column from Section 4. Test Cases column
will be filled by `/test-plan-create-cases`. Coverage column will
be filled by `/coverage-assessment`. Leave both empty until then.}

| Interface | Test Cases | Coverage |
|-----------|------------|----------|
| {interface} | | |

### 9.3 Document Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | {today_date} | Initial test plan |

---

## End of Test Plan

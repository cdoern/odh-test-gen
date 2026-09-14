# Test Case Implementation Generator - Reference Documentation

This document provides reference information for the `/test-plan-case-implement` skill.

For execution instructions, see [SKILL.md](SKILL.md).

---

## Sub-Agents (Forked, Non-User-Invocable)

This skill uses the following forked sub-agents:

### test-plan-generate-test-file
- **When**: Step 4 (test code generation from TC specs)
- **Input**: file path, TCs for that file, function names, framework, conventions, pattern guide, repo instructions, common setup, target repo path, feature dir
- **Output**: Complete test file content plus quality summary (written to `/tmp/test_plan_results/file_{i}.json`)
- **Purpose**: Generate one test file matching repository conventions, including scoring and auto-revision
- **Parallelization**: Invoked once per mapped file, all run in parallel
- **user-invocable**: false
- **Note**: Scoring via `test-plan-score-test-function` happens inside this sub-agent, not in the parent

---

## Utility Scripts

This skill uses the following utility scripts:

### scripts/utils/repo_utils.py
- `find_known_repo(repo_type)` - Locate known repos ('odh-test-context', 'tiger-team'), returns (path, clone_url)
- `find_target_repo(repo_name)` - Find target repo by org/repo name or local git clone path
- `find_repo_in_common_locations(repo_name)` - Search common locations for a repository
- `clone_repo(repo_url, target_path)` - Clone Git repository from GitHub
- `map_components_to_repos(components, odh_path)` - Map component names to GitHub repos
- `load_repo_test_context(repo_name, odh_path)` - Load test context JSON from odh-test-context
- `extract_conventions_from_context(test_context)` - Extract conventions from odh-test-context
- `get_framework(test_context)` - Get test framework from odh-test-context data

### scripts/utils/schemas.py
- `SCHEMAS` - Schema definitions for all artifact types
- `validate(data, schema_type)` - Validate frontmatter against schema
- `apply_defaults(data, schema_type)` - Apply default values
- `detect_schema_type(path)` - Detect schema from filename
- `get_schema_yaml(schema_type)` - Get schema as YAML string
- `ValidationError` - Exception for validation failures

### scripts/utils/frontmatter_utils.py
- `read_frontmatter(file_path)` - Read YAML frontmatter from file, returns (dict, body)
- `read_frontmatter_validated(file_path, schema_type)` - Read and validate frontmatter
- `write_frontmatter(file_path, data, schema_type)` - Write validated frontmatter
- `update_frontmatter(file_path, updates, schema_type)` - Update specific fields

### scripts/utils/tc_parser.py
- `parse_tc_file(tc_file, read_frontmatter_func)` - Parse TC file into structured data (extracts Objective, Preconditions, Test Steps, Expected Results)

### scripts/utils/repo_discovery.py
- `extract_repo_indicators(testplan_path, tc_files)` - Extract components and endpoints from TestPlan.md using hardcoded keywords

### scripts/utils/test_analyzer.py
- `identify_common_setup_requirements(test_cases)` - Identify preconditions used by 2+ TCs (framework-agnostic)

### scripts/utils/component_map.py
- `COMPONENT_REPO_MAP` - Authoritative component → repo mapping from odh-build-metadata

---

## Dependencies

### Required
- **Python 3.10+** - For test code generation and validation
- **uv** - For running frontmatter scripts
- **git** - For cloning repositories
- **gh CLI** - For fetching artifacts from GitHub branches (if feature source is remote)

### Recommended (High Value)
- **odh-test-context** repository at `~/Code/odh-test-context` (or custom path)
  - Provides pre-analyzed test context for ~162 opendatahub-io repos
  - Includes: framework detection, conventions, linting, container recipes, agent_readiness
  - **Significantly improves** test quality and repository convention detection
  - Source: <https://github.com/opendatahub-io/odh-test-context>
  - If missing: Skill offers to clone or proceed with manual discovery

- **Red-Hat-Quality-Tiger-Team** repository at `~/Code/Red-Hat-Quality-Tiger-Team` (or custom path)
  - Provides test pattern guides (go-tests.md, typescript-unit-tests.md, cypress-tests.md, testing-standards.md)
  - Guides provide code patterns, examples, and anti-patterns for test generation
  - Source: <https://github.com/RedHatQE/Red-Hat-Quality-Tiger-Team>
  - If missing: Skill offers to clone or auto-generate via Tiger Team's test-rules-generator

### Optional
- **podman** or **docker** - For container validation of generated tests (if odh-test-context provides container_recipe)
- **pytest** - If target repo uses pytest framework

---

## How Dependencies Work Together

### For Test Code Generation (Step 4):
```
Tiger Team pattern guides     odh-test-context         test-plan-generate-test-file
(code patterns, examples)  +  (basic conventions)  →   (sub-agent)
          ↓                           ↓                       ↓
   "Use Ginkgo BeforeSuite,    "Framework: pytest,      Generated test code
    mock with gofakeit,         file pattern: test_*.py" matching repo style
    assert with Gomega"  
```

**Component Roles**:
1. **odh-test-context** - Repo structure data (framework, dirs, agent_readiness) → Used for test generation
2. **Tiger Team pattern guides** - Code style guides (how to write tests) → Used by test generator sub-agent

---

## What this skill does NOT do

- Does NOT generate test plan or test case specifications — use `/test-plan-create` and `/test-plan-create-cases` for that
- Does NOT guarantee passing tests — optional container validation (Step 5.3, when
  `validate_in_container` is true) may run lint and `pytest`, but live-cluster validation remains
  manual; Step 5.4 explicitly prompts for it and the summary flags unverified coverage, so generated
  tests must still be reviewed and run (against a live cluster) manually before they are trusted
- Does NOT commit tests to target repository — user must review, run, and commit manually
- Does NOT guarantee 100% correct test code — always requires manual review and enhancement
- Does NOT resolve test failures or debug test issues — troubleshooting is manual
- Does NOT update test plan coverage metrics — use `/coverage-assessment` for that
- Does NOT create fixtures or test data files automatically — only suggests them in summary report

**Supported test frameworks**: pytest, unittest, Playwright (Python); Ginkgo/Gomega, go-testing (Go); Jest, Cypress (TypeScript/JavaScript)

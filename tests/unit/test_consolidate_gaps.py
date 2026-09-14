"""
Unit tests for scripts/consolidate_gaps.py consolidate_gaps() function.

Tests the pure function in isolation with mock input (no file I/O).
CLI tests are in tests/integration/test_consolidate_gaps_cli.py.
"""

import pytest

from scripts.utils.consolidate_gaps import consolidate_gaps, is_actionability_advisory_concern, read_sources
from tests.consts.gaps_constants import (
    ACTIONABILITY_PRODUCT_ADVISORY_CASES,
    GAPS_ALL_EMPTY,
    GAPS_BULLET_THEN_NO_GAPS_LINE,
    GAPS_CAPITALIZED_RESOLVED_BY,
    GAPS_DOC_TYPE_ONLY_PUNCT,
    GAPS_DOC_TYPE_PERIOD,
    GAPS_DOC_TYPE_PERIOD_APISPEC,
    GAPS_EMPTY_UPPERCASE_HEADING,
    GAPS_ENDPOINTS_DUPLICATE,
    GAPS_ENDPOINTS_EXACT_DUP,
    GAPS_ENDPOINTS_FULL_ANALYZER_DOC,
    GAPS_ENDPOINTS_SYNONYM_NORMALIZATION,
    GAPS_ENDPOINTS_UNRECOGNIZED,
    GAPS_INFRA_SINGLETON,
    GAPS_LOWERCASE_HEADING,
    GAPS_MALFORMED_NO_RESOLVED_BY,
    GAPS_NO_HEADING,
    GAPS_PLAIN_HYPHEN_SEPARATOR,
    GAPS_PREFIX_SIBLING_HEADING,
    GAPS_RISKS_DUPLICATE,
    GAPS_RISKS_EXACT_DUP,
    GAPS_RISKS_SYNONYM_NORMALIZATION,
    GAPS_TRAILING_WHITESPACE_HEADING,
    GAPS_UPPERCASE_HEADING,
    GAPS_WITH_TRAILING_SECTION,
    GAPS_WRAPPED_BULLET,
    GAPS_WRAPPED_THEN_NORMAL,
)


class TestActionabilityAdvisoryFiltering:
    @pytest.mark.parametrize(
        "concern_text, advisory_gaps, expected_filtered",
        ACTIONABILITY_PRODUCT_ADVISORY_CASES,
        ids=(
            "openshift-advisory-filters-openshift-concern",
            "openshift-advisory-retains-rhoai-concern",
            "rhoai-advisory-filters-rhoai-concern",
            "rhoai-advisory-retains-openshift-concern",
            "rhoai-advisory-retains-material-operator-compatibility-concern",
            "rhoai-advisory-retains-material-operator-version-concern",
        ),
    )
    def test_advisory_filtering_is_product_specific(self, concern_text, advisory_gaps, expected_filtered):
        concern = {"text": concern_text}

        assert is_actionability_advisory_concern(concern, list(advisory_gaps)) is expected_filtered


class TestConsolidateSameGapArtifact:
    """Two sub-agents flagging same artifact in different wording collapse into one entry."""

    def test_same_normalized_doc_type_differently_worded(self):
        """
        Differently-worded concerns of the same doc type stay distinct within one group.
        The group is flagged by all contributing sources.
        gap_count counts doc-type groups (3 here: API spec, ADR, design doc).
        """
        sources = {
            "endpoints": GAPS_ENDPOINTS_DUPLICATE,
            "risks": GAPS_RISKS_DUPLICATE,
            "infra": GAPS_INFRA_SINGLETON,
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 3, "Should have ADR, API spec, design doc groups"
        assert result["status"] == "Open"

        # Find the API spec group
        api_spec_group = next((g for g in result["groups"] if g["doc_type"] == "API spec"), None)
        assert api_spec_group is not None, "API spec group should exist"
        assert len(api_spec_group["concerns"]) == 3, "Should have 3 distinct concerns"

        # Check that the group-level source union includes both endpoints and risks
        all_sources_in_group = {s for c in api_spec_group["concerns"] for s in c["sources"]}
        assert all_sources_in_group == {"endpoints", "risks"}, (
            "API spec group should be flagged by both endpoints and risks (union of concern sources)"
        )

        # Body should mention both sources at the group level
        assert "flagged by: endpoints, risks" in result["body"] or "flagged by: risks, endpoints" in result["body"]

    def test_exact_duplicate_concern_text_same_doc_type(self):
        """Two sources, identical concern text + same doc type → one group, one concern, both sources tagged."""
        sources = {
            "endpoints": GAPS_ENDPOINTS_EXACT_DUP,
            "risks": GAPS_RISKS_EXACT_DUP,
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 1, "Should have one API spec group"

        api_spec_group = result["groups"][0]
        assert api_spec_group["doc_type"] == "API spec"
        assert len(api_spec_group["concerns"]) == 1, "Identical concerns should be deduped"

        concern = api_spec_group["concerns"][0]
        assert sorted(concern["sources"]) == ["endpoints", "risks"], "Both sources should be tagged"
        assert "Catalog endpoint request/response schema is undefined" in concern["text"]

    def test_compound_secondary_type_differs_still_merges(self):
        """Same concern, two analyzers each answer ADR plus a
        DIFFERENT secondary guess ("/" vs " or " separator). Both must collapse into one ADR
        group instead of forming two separate near-duplicate buckets.
        """
        concern_text = "Feature flag gating unclear"
        sources = {
            "endpoints": f"## Gaps\n\n- **{concern_text}** — would be resolved by: ADR / design doc\n",
            "risks": f"## Gaps\n\n- **{concern_text}** — would be resolved by: ADR or feature refinement\n",
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 1, "Both compound guesses should merge into one ADR group"
        assert result["groups"][0]["doc_type"] == "ADR"
        assert len(result["groups"][0]["concerns"]) == 1, "Identical concern text should dedup within the group"
        assert sorted(result["groups"][0]["concerns"][0]["sources"]) == ["endpoints", "risks"]


class TestConsolidateDifferentGaps:
    """Distinct gaps from different sub-agents are not over-merged."""

    def test_different_doc_types_stay_separate(self):
        """Two sources, different doc types → two groups, gap_count=2."""
        sources = {
            "endpoints": GAPS_ENDPOINTS_DUPLICATE,  # API spec
            "risks": """## Gaps\n\n- **KServe CSI configuration details are missing** — would be resolved by: ADR\n""",
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 2, "Should have two groups (API spec, ADR)"

        doc_types = {g["doc_type"] for g in result["groups"]}
        assert doc_types == {"API spec", "ADR"}

    def test_distinct_concerns_same_doc_type_counted_as_one_group(self):
        """Two genuinely distinct concerns with the same doc type → gap_count=1, both preserved
        as sub-bullets under that type. This is the intended semantic: gap_count = number of
        missing document types, not number of distinct concerns. Distinct concerns are still
        visible as sub-bullets; they are not lost."""
        sources = {
            "endpoints": "## Gaps\n\n- **Pagination parameters undefined** — would be resolved by: API spec\n",
            "risks": "## Gaps\n\n- **Auth error response codes undefined** — would be resolved by: API spec\n",
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 1, "Two distinct concerns, same doc type → one group (one missing document type)"
        assert len(result["groups"]) == 1
        api_spec_group = result["groups"][0]
        assert api_spec_group["doc_type"] == "API spec"
        assert len(api_spec_group["concerns"]) == 2, "Both distinct concerns are preserved as sub-bullets"
        concern_texts = {c["text"] for c in api_spec_group["concerns"]}
        assert concern_texts == {"Pagination parameters undefined", "Auth error response codes undefined"}


class TestConsolidateGapsFrontmatter:
    """gap_count in frontmatter matches deduplicated entry count."""

    def test_gap_count_equals_number_of_groups(self):
        """gap_count = number of top-level groups (document types), not raw concern count."""
        sources = {
            "endpoints": GAPS_ENDPOINTS_DUPLICATE,  # 2 concerns, both API spec
            "risks": GAPS_RISKS_DUPLICATE,  # 2 concerns: 1 API spec, 1 ADR
            "infra": GAPS_INFRA_SINGLETON,  # 1 concern: design doc
        }

        result = consolidate_gaps(sources)

        # API spec, ADR, design doc → 3 groups
        assert result["gap_count"] == 3
        assert len(result["groups"]) == 3
        assert result["gap_count"] == len(result["groups"]), "gap_count must equal groups length"


class TestConsolidateGapsSynonymNormalization:
    """Synonym normalization: common variants map to canonical doc types."""

    @pytest.mark.parametrize(
        "input_text,expected_canonical",
        [
            ("API specification", "API spec"),
            ("api spec", "API spec"),
            ("openapi", "API spec"),
            ("swagger", "API spec"),
            ("adr", "ADR"),
            ("architecture decision record", "ADR"),
            ("refinement", "feature refinement"),
            ("feature refinement", "feature refinement"),
            ("design doc", "design doc"),
            ("design document", "design doc"),
            ("feature refinement (PM/Engineering decision)", "feature refinement"),
            ("internal notes / API spec", "API spec"),
        ],
    )
    def test_synonym_normalization(self, input_text, expected_canonical):
        """Synonyms normalize to canonical form, including a parenthetical elaboration on an
        otherwise-canonical answer, and a compound answer where the canonical type is buried
        as the second segment rather than the first."""
        gap_text = f"""## Gaps\n\n- **Test concern** — would be resolved by: {input_text}\n"""
        sources = {"endpoints": gap_text}

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 1
        assert result["groups"][0]["doc_type"] == expected_canonical

    def test_different_synonyms_group_together(self):
        """Different synonyms for same doc type collapse into one group."""
        sources = {
            "endpoints": GAPS_ENDPOINTS_SYNONYM_NORMALIZATION,  # "openapi"
            "risks": GAPS_RISKS_SYNONYM_NORMALIZATION,  # "refinement"
        }

        result = consolidate_gaps(sources)

        # "openapi" → "API spec", "refinement" → "feature refinement"
        assert result["gap_count"] == 2
        doc_types = {g["doc_type"] for g in result["groups"]}
        assert doc_types == {"API spec", "feature refinement"}


class TestConsolidateGapsUnrecognizedDocType:
    """Unrecognized `resolved-by` → its own bucket, not crash, not merged into canonical."""

    def test_unrecognized_doc_type_creates_own_bucket(self):
        """Unrecognized doc type is kept as-is (cleaned), not dropped."""
        sources = {
            "endpoints": GAPS_ENDPOINTS_UNRECOGNIZED,  # "runbook"
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 1
        assert result["groups"][0]["doc_type"] == "runbook"

    def test_unrecognized_not_merged_with_canonical(self):
        """Unrecognized doc type does not merge into a canonical group."""
        sources = {
            "endpoints": """## Gaps\n\n- **Test** — would be resolved by: API spec\n""",
            "risks": """## Gaps\n\n- **Test2** — would be resolved by: runbook\n""",
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 2
        doc_types = {g["doc_type"] for g in result["groups"]}
        assert doc_types == {"API spec", "runbook"}

    def test_unrecognized_compound_kept_as_whole(self):
        """Fail-open: if neither segment of a compound answer matches a canonical type, the
        whole compound is kept as one bucket, not split or dropped."""
        sources = {
            "endpoints": """## Gaps\n\n- **Some odd gap** — would be resolved by: runbook / playbook\n""",
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 1
        assert result["groups"][0]["doc_type"] == "runbook / playbook"


class TestConsolidateGapsMalformedBullet:
    """Malformed bullet (no 'resolved by') → kept under '(unspecified)', not dropped."""

    def test_malformed_bullet_kept_under_unspecified(self):
        """Bullet without 'resolved by' clause is bucketed under '(unspecified)'."""
        sources = {
            "endpoints": GAPS_MALFORMED_NO_RESOLVED_BY,
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 1
        assert result["groups"][0]["doc_type"] == "(unspecified)"
        assert "Some concern that lacks the resolved-by clause" in result["groups"][0]["concerns"][0]["text"]

    def test_malformed_bullet_not_dropped(self):
        """Fail-open: malformed bullets must appear in output, not silently lost."""
        sources = {
            "endpoints": GAPS_MALFORMED_NO_RESOLVED_BY,
            "risks": """## Gaps\n\n- **Valid concern** — would be resolved by: ADR\n""",
        }

        result = consolidate_gaps(sources)

        # Should have ADR + (unspecified)
        assert result["gap_count"] == 2
        doc_types = {g["doc_type"] for g in result["groups"]}
        assert doc_types == {"ADR", "(unspecified)"}


class TestConsolidateGapsNoGaps:
    """All sources 'No gaps identified.' → gap_count=0, status='Resolved', body says 'No gaps'."""

    def test_all_sources_no_gaps_identified(self):
        """All sources say 'No gaps identified' → count=0, status=Resolved."""
        sources = {
            "endpoints": GAPS_ALL_EMPTY,
            "risks": GAPS_ALL_EMPTY,
            "infra": GAPS_ALL_EMPTY,
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 0
        assert result["status"] == "Resolved"
        assert "No gaps identified" in result["body"]

    def test_empty_gap_sections_treated_as_no_gaps(self):
        """Empty markdown after '## Gaps' header → treated as no gaps."""
        sources = {
            "endpoints": "## Gaps\n\n",
            "risks": "## Gaps\n\n",
            "infra": "## Gaps\n\n",
        }

        result = consolidate_gaps(sources)

        assert result["gap_count"] == 0
        assert result["status"] == "Resolved"


class TestConsolidateSingletonGroupFormat:
    """Singleton groups now render as multi-line (uniform structure with multi-concern groups)."""

    def test_singleton_group_renders_multiline(self):
        """
        A single-concern group renders as:
        - **doc type** — flagged by: source
          - concern text
        NOT the old one-line: - **doc type** — flagged by: source — concern text
        """
        sources = {
            "infra": GAPS_INFRA_SINGLETON,
        }

        result = consolidate_gaps(sources, feature_name="Test Feature")

        assert result["gap_count"] == 1
        assert result["status"] == "Open"

        # The body must contain the two-line form
        expected_header_line = "- **design doc** — flagged by: infra"
        expected_sub_bullet = "  - Database failover behavior is not documented"

        assert expected_header_line in result["body"], "Missing header line in singleton group"
        assert expected_sub_bullet in result["body"], "Missing indented sub-bullet in singleton group"

        # The old one-line form must NOT appear
        old_one_line_form = "- **design doc** — flagged by: infra — Database failover behavior is not documented"
        assert old_one_line_form not in result["body"], "Old one-line singleton form found (should be two-line)"


class TestConsolidateGapsSectionExtraction:
    """Extract only the ## Gaps section from full analyzer documents."""

    def test_full_analyzer_doc_excludes_non_gaps_bullets(self):
        """
        A full analyzer document with non-gaps sections (e.g. ## Test Tools with plain bullets)
        must only parse bullets from the ## Gaps section. Plain bullets before/outside ## Gaps
        must NOT appear as concerns or create an '(unspecified)' bucket.
        """
        sources = {
            "endpoints": GAPS_ENDPOINTS_FULL_ANALYZER_DOC,
        }

        result = consolidate_gaps(sources, feature_name="Test Feature")

        # Should have exactly ONE group (API spec), NOT an (unspecified) bucket
        assert result["gap_count"] == 1, "Should have only API spec group, not (unspecified) bucket"
        assert result["groups"][0]["doc_type"] == "API spec"
        assert len(result["groups"][0]["concerns"]) == 1
        assert "Auth flow undefined" in result["groups"][0]["concerns"][0]["text"]

        # The plain bullets (pytest, playwright) must NOT appear
        assert "pytest" not in result["body"]
        assert "playwright" not in result["body"]
        # Must NOT have created an (unspecified) bucket
        assert "(unspecified)" not in result["body"]

    def test_gaps_section_with_trailing_section(self):
        """
        Bullets after a following level-2 heading (e.g. ## Implementation Notes) must be excluded.
        Only bullets between ## Gaps and the next ## heading (or EOF) are parsed.
        """
        sources = {
            "endpoints": GAPS_WITH_TRAILING_SECTION,
        }

        result = consolidate_gaps(sources, feature_name="Test Feature")

        assert result["gap_count"] == 1
        assert result["groups"][0]["doc_type"] == "ADR"
        assert len(result["groups"][0]["concerns"]) == 1
        assert "Missing ADR" in result["groups"][0]["concerns"][0]["text"]

        # Bullets from the trailing ## Implementation Notes section must NOT appear
        assert "More bullets here" not in result["body"]
        assert "These should NOT be parsed" not in result["body"]

    def test_prefix_sibling_heading_is_not_parsed_as_gaps(self):
        """A later '## Gaps extra' heading must not steal or extend the ## Gaps section."""
        sources = {"endpoints": GAPS_PREFIX_SIBLING_HEADING}

        result = consolidate_gaps(sources, feature_name="Test Feature")

        assert result["gap_count"] == 1
        assert result["groups"][0]["doc_type"] == "API spec"
        assert "Auth flow undefined" in result["groups"][0]["concerns"][0]["text"]
        assert "This must not be parsed as a gap" not in result["body"]
        assert "ADR" not in {g["doc_type"] for g in result["groups"]}


class TestConsolidateGapsDeterministicOrdering:
    """Deterministic ordering: canonical order regardless of input source order."""

    def test_canonical_order_regardless_of_input(self):
        """Groups appear in CANONICAL_DOC_TYPES order, then alphabetic, then (unspecified) last."""
        # Feed in reverse order: design doc, feature refinement, API spec, ADR
        sources = {
            "endpoints": """## Gaps\n\n- **Test** — would be resolved by: design doc\n""",
            "risks": """## Gaps\n\n- **Test2** — would be resolved by: feature refinement\n""",
            "infra": """## Gaps

- **Test3** — would be resolved by: API spec
- **Test4** — would be resolved by: ADR
""",
        }

        result = consolidate_gaps(sources)

        # Expected order: ADR, API spec, feature refinement, design doc
        doc_types = [g["doc_type"] for g in result["groups"]]
        assert doc_types == ["ADR", "API spec", "feature refinement", "design doc"]

    def test_unrecognized_buckets_alphabetically_after_canonical(self):
        """Unrecognized doc types sort alphabetically after canonical ones."""
        sources = {
            "endpoints": """## Gaps

- **Test1** — would be resolved by: zebra-doc
- **Test2** — would be resolved by: alpha-doc
- **Test3** — would be resolved by: ADR
""",
        }

        result = consolidate_gaps(sources)

        doc_types = [g["doc_type"] for g in result["groups"]]
        # ADR (canonical), then alpha-doc, zebra-doc (alphabetic)
        assert doc_types == ["ADR", "alpha-doc", "zebra-doc"]

    def test_unspecified_always_last(self):
        """(unspecified) bucket always appears last."""
        sources = {
            "endpoints": """## Gaps

- **Malformed**
- **Valid** — would be resolved by: ADR
- **Another** — would be resolved by: zebra-doc
""",
        }

        result = consolidate_gaps(sources)

        doc_types = [g["doc_type"] for g in result["groups"]]
        assert doc_types[-1] == "(unspecified)", "unspecified must be last"
        assert doc_types == ["ADR", "zebra-doc", "(unspecified)"]


class TestConsolidateGapsCaseInsensitiveHeading:
    """Case-insensitive heading extraction."""

    @pytest.mark.parametrize(
        "fixture",
        [
            pytest.param(GAPS_UPPERCASE_HEADING, id="uppercase"),
            pytest.param(GAPS_LOWERCASE_HEADING, id="lowercase"),
            pytest.param(GAPS_TRAILING_WHITESPACE_HEADING, id="trailing-whitespace"),
        ],
    )
    def test_case_variants_exclude_prior_section(self, fixture):
        """
        All heading case/whitespace variants (GAPS, gaps, 'Gaps   ') must extract
        ONLY the Gaps section, excluding prior sections (Test Tools with pytest/playwright).
        """
        sources = {"endpoints": fixture}

        result = consolidate_gaps(sources, feature_name="Test Feature")

        # Contract: exactly ONE group (API spec), NOT an (unspecified) bucket
        assert result["gap_count"] == 1, "Should have only API spec group, not (unspecified) bucket"
        assert result["groups"][0]["doc_type"] == "API spec"
        assert len(result["groups"][0]["concerns"]) == 1
        assert "Auth flow undefined" in result["groups"][0]["concerns"][0]["text"]

        # The plain bullets from Test Tools (pytest, playwright) must NOT appear
        assert "pytest" not in result["body"]
        assert "playwright" not in result["body"]
        # Must NOT have created an (unspecified) bucket
        assert "(unspecified)" not in result["body"]

    def test_empty_case_variant_heading_yields_zero_gaps(self):
        """
        An empty but present case-variant heading (e.g. '## GAPS\n\n') yields gap_count 0,
        NOT fallback-to-whole-doc.
        """
        sources = {"endpoints": GAPS_EMPTY_UPPERCASE_HEADING}

        result = consolidate_gaps(sources, feature_name="Test Feature")

        assert result["gap_count"] == 0
        assert result["status"] == "Resolved"


class TestConsolidateGapsNoHeading:
    """Coverage lock, may be green immediately."""

    def test_bare_bullet_no_heading(self):
        """
        Input a bare string (no '## Gaps' heading). Contract: fail-open, bullet never lost.
        """
        sources = {"endpoints": GAPS_NO_HEADING}

        result = consolidate_gaps(sources, feature_name="Test Feature")

        assert result["gap_count"] == 1
        assert result["groups"][0]["doc_type"] == "ADR"
        assert "Some gap" in result["groups"][0]["concerns"][0]["text"]


class TestConsolidateGapsWrappedBullet:
    """Wrapped/multi-line bullet parsing."""

    def test_wrapped_resolved_by_clause(self):
        """
        A bullet whose resolved-by clause wraps to the next physical line.
        Contract: a logical bullet = the '- ' line plus following non-blank lines not starting
        with '- ', joined by a single space, terminated by blank line / next '- ' / EOF.
        """
        sources = {"endpoints": GAPS_WRAPPED_BULLET}

        result = consolidate_gaps(sources, feature_name="Test Feature")

        assert result["gap_count"] == 1, "Should have ADR group, not (unspecified)"
        assert result["groups"][0]["doc_type"] == "ADR", f"Expected ADR, got {result['groups'][0]['doc_type']}"
        assert "Auth token refresh path is undocumented" in result["groups"][0]["concerns"][0]["text"]

    def test_wrapped_bullet_followed_by_normal(self):
        """
        A wrapped bullet followed by another normal bullet.
        Proves the join terminates correctly and does not merge the next bullet.
        """
        sources = {"endpoints": GAPS_WRAPPED_THEN_NORMAL}

        result = consolidate_gaps(sources, feature_name="Test Feature")

        assert result["gap_count"] == 2, "Should have ADR and API spec groups"
        doc_types = {g["doc_type"] for g in result["groups"]}
        assert doc_types == {"ADR", "API spec"}

        # Both concerns should be distinct
        adr_group = next((g for g in result["groups"] if g["doc_type"] == "ADR"), None)
        api_group = next((g for g in result["groups"] if g["doc_type"] == "API spec"), None)

        assert adr_group is not None
        assert api_group is not None
        assert len(adr_group["concerns"]) == 1
        assert len(api_group["concerns"]) == 1
        assert "Auth token refresh path" in adr_group["concerns"][0]["text"]
        assert "Another gap" in api_group["concerns"][0]["text"]

    def test_bullet_followed_by_no_gaps_line_not_absorbed(self):
        """
        "No gaps identified." line immediately after a bullet
        with no blank line must NOT be absorbed into the bullet.

        Contract: _coalesce_bullets must treat "No gaps identified." as a standalone non-bullet
        line (ignored), not a continuation of the preceding bullet. The bullet's doc_type must
        remain "ADR", not corrupted to "ADR No gaps identified.".
        """
        sources = {"endpoints": GAPS_BULLET_THEN_NO_GAPS_LINE}

        result = consolidate_gaps(sources, feature_name="Test Feature")

        assert result["gap_count"] == 1, f"Expected 1 gap, got {result['gap_count']}"
        assert result["groups"][0]["doc_type"] == "ADR", (
            f"Expected doc_type 'ADR', got '{result['groups'][0]['doc_type']}' "
            "(the 'No gaps identified.' line must NOT be absorbed into the bullet)"
        )


class TestConsolidateGapsDocTypePunctuation:
    """Doc-type trailing punctuation strip and separator tolerance."""

    @pytest.mark.parametrize(
        "gap_source_text,expected_doc_type",
        [
            pytest.param(GAPS_DOC_TYPE_PERIOD, "ADR", id="trailing-period-adr"),
            pytest.param(GAPS_DOC_TYPE_PERIOD_APISPEC, "API spec", id="trailing-period-apispec"),
            pytest.param(GAPS_PLAIN_HYPHEN_SEPARATOR, "ADR", id="hyphen-separator"),
            pytest.param(GAPS_CAPITALIZED_RESOLVED_BY, "ADR", id="capitalized-resolved-by"),
        ],
    )
    def test_doc_type_punctuation_and_separator_tolerance(self, gap_source_text, expected_doc_type):
        """
        Doc type parsing handles trailing punctuation, separator variants, and case variants.
        """
        sources = {"endpoints": gap_source_text}

        result = consolidate_gaps(sources, feature_name="Test Feature")

        assert result["gap_count"] == 1, f"Expected 1 gap, got {result['gap_count']}"
        assert result["groups"][0]["doc_type"] == expected_doc_type, (
            f"Expected '{expected_doc_type}', got '{result['groups'][0]['doc_type']}'"
        )


class TestConsolidateGapsDocTypeNormalization:
    """Doc-type normalization edge cases."""

    def test_all_punctuation_doc_type_not_collapsed_to_empty(self):
        """
        A doc-type that is only punctuation (e.g., a lone ".")
        must NOT normalize to empty string.

        Contract: _normalize_doc_type strips trailing punctuation, but when that empties
        the value, it must fall back to the pre-strip cleaned value. A bullet with
        doc-type "." must produce doc_type == ".", NOT "".
        """
        sources = {"endpoints": GAPS_DOC_TYPE_ONLY_PUNCT}

        result = consolidate_gaps(sources, feature_name="Test Feature")

        assert result["gap_count"] == 1, f"Expected 1 gap, got {result['gap_count']}"
        assert result["groups"][0]["doc_type"] == ".", (
            f"Expected doc_type '.', got '{result['groups'][0]['doc_type']}' "
            "(all-punctuation doc-type must NOT collapse to empty string)"
        )


class TestReadSources:
    def test_reads_name_path_pairs(self, tmp_path):
        path = tmp_path / ".analysis-endpoints.md"
        path.write_text("## Gaps\n\nNo gaps identified.\n")

        sources = read_sources([f"endpoints={path}"])

        assert sources == {"endpoints": "## Gaps\n\nNo gaps identified.\n"}

    @pytest.mark.parametrize(
        "make_source_args,expected_error",
        [
            (lambda _path: ["endpoints"], "invalid_source_argument"),
            (lambda path: [f"endpoints={path}"], "source_file_not_found"),
        ],
        ids=["no-equals", "missing-file"],
    )
    def test_raises_for_unreadable_sources(self, tmp_path, make_source_args, expected_error):
        missing = tmp_path / ".analysis-endpoints.md"

        with pytest.raises(ValueError, match=expected_error):
            read_sources(make_source_args(missing))

#!/usr/bin/env python3
"""Consolidate gap bullets from multiple analyzer sub-agents into deduplicated,
per-missing-document groups.

Each analyzer (`endpoints`, `risks`, `infra`) reports its own `## Gaps` markdown
section using the fixed bullet shape:

    - **{gap description}** — would be resolved by: {ADR / API spec / feature refinement / design doc}

Two analyzers frequently flag the same missing artifact in different wording. This
script groups gap bullets by their normalized `resolved-by` document type — the
dedup key — so `gap_count` reflects the number of missing documents, not the raw
number of gap bullets across all sub-agents.

Imported by consolidate_gaps_and_stamp.py for gap consolidation and source file reading.
"""

import re
from collections.abc import Callable

from scripts.utils.markdown_utils import extract_section

CANONICAL_DOC_TYPES = ["ADR", "API spec", "feature refinement", "design doc"]

UNSPECIFIED = "(unspecified)"

ACTIONABILITY_VERSION_LABELS = ("OpenShift version", "RHOAI version")
ACTIONABILITY_TEST_DATA_GAP = "test data formats and examples"

_SYNONYMS = {
    "adr": "ADR",
    "architecture decision record": "ADR",
    "api spec": "API spec",
    "api specification": "API spec",
    "openapi": "API spec",
    "swagger": "API spec",
    "refinement": "feature refinement",
    "feature refinement": "feature refinement",
    "design doc": "design doc",
    "design document": "design doc",
}

# Matches: - **{desc}** — would be resolved by: {type}  (tolerates em-dash/hyphen,
# case-insensitive "resolved by").
_BULLET_RE = re.compile(
    r"^-\s+\*\*(?P<desc>.+?)\*\*\s*[—-]\s*.*resolved by:\s*(?P<doc_type>.+?)\s*$",
    re.IGNORECASE,
)

# A level-2 "Gaps" heading, tolerant of case (GAPS, gaps, Gaps) and trailing whitespace.
_GAPS_HEADING_RE = re.compile(r"^#{2}\s+gaps\s*$", re.IGNORECASE)

# A parenthetical elaboration tacked onto an otherwise-canonical answer, e.g.
# "feature refinement (PM/Engineering decision)".
_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)")

# Separator an analyzer used to join a compound answer, e.g. "ADR / design doc" or
# "ADR or design doc".
_COMPOUND_SEPARATOR_RE = re.compile(r"\s*/\s*|\s+or\s+", re.IGNORECASE)

_VERSION_ONLY_GAP_RE = re.compile(
    r"^(?=.*\b(?:open\s*shift|ocp|rhoa[i]?|operator)\b)"
    r"(?=.*\b(?:version|build|release)\b)",
    re.IGNORECASE,
)
_VERSION_PRODUCT_PATTERNS = {
    ACTIONABILITY_VERSION_LABELS[0]: re.compile(r"\b(?:open\s*shift|ocp)\b", re.IGNORECASE),
    ACTIONABILITY_VERSION_LABELS[1]: re.compile(r"\brhoa[i]?\b", re.IGNORECASE),
}
_OPERATOR_VERSION_REQUIREMENT_RE = re.compile(
    r"\boperator(?:'s)?[\s/-]+(?:versions?|builds?|releases?)\b", re.IGNORECASE
)
_TEST_DATA_ONLY_GAP_RE = re.compile(
    r"^(?=.*\b(?:test[\s-]+data|fixtures?|samples?)\b)"
    r"(?=.*\b(?:formats?|examples?|samples?|fixtures?|schema)\b)",
    re.IGNORECASE,
)
_TEST_DATA_SCHEMA_CONTEXT_RE = re.compile(r"\b(?:test[\s-]+data|fixtures?|payloads?|samples?)\b", re.IGNORECASE)
_MATERIAL_SCHEMA_CONTEXT_RE = re.compile(
    r"\b(?:api|service|database)\b.{0,40}\bschema\b|\bschema\b.{0,40}\b(?:api|service|database)\b",
    re.IGNORECASE,
)
_MATERIAL_GAP_RE = re.compile(
    r"\b(?:api|service|endpoint|request|response|schema|contract|contracts|role|roles|permission|permissions|"
    r"rbac|security|authentication|authorization|access|credential|credentials|token|tokens|scope|scopes|"
    r"validation|validate|criteria|compatibility|compatible|operational|operation|webhook|network|deployment|"
    r"migration|latency|performance|provisioning|runtime|availability|reliability|timeout|resource|resources|"
    r"namespace|namespaces)\b",
    re.IGNORECASE,
)

_VERSION_ONLY_TERMS = frozenset(
    {
        "open",
        "shift",
        "openshift",
        "ai",
        "ocp",
        "rhoai",
        "operator",
        "cluster",
        "platform",
        "version",
        "versions",
        "build",
        "builds",
        "release",
        "releases",
        "number",
        "numbers",
        "exact",
        "pinned",
        "specific",
        "required",
        "requirement",
        "requirements",
        "target",
        "desired",
        "supported",
        "minimum",
        "maximum",
        "min",
        "max",
        "range",
        "ranges",
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "for",
        "in",
        "on",
        "to",
        "be",
        "is",
        "are",
        "was",
        "were",
        "as",
        "at",
        "by",
        "before",
        "after",
        "during",
        "not",
        "no",
        "missing",
        "absent",
        "unavailable",
        "unspecified",
        "specified",
        "unknown",
        "tbd",
        "pending",
        "latest",
        "current",
        "defined",
        "provided",
        "confirmed",
        "determined",
        "selected",
        "decided",
        "available",
        "value",
        "values",
        "detail",
        "details",
        "environment",
        "test",
        "testing",
        "setup",
        "execution",
        "stable",
    }
)

_TEST_DATA_ONLY_TERMS = frozenset(
    {
        "test",
        "data",
        "format",
        "formats",
        "example",
        "examples",
        "sample",
        "samples",
        "fixture",
        "fixtures",
        "payload",
        "payloads",
        "schema",
        "value",
        "values",
        "concrete",
        "specific",
        "required",
        "requirement",
        "requirements",
        "missing",
        "absent",
        "unavailable",
        "unspecified",
        "specified",
        "unknown",
        "tbd",
        "incomplete",
        "not",
        "is",
        "are",
        "was",
        "were",
        "be",
        "to",
        "and",
        "or",
        "of",
        "for",
        "the",
        "a",
        "an",
        "with",
        "provided",
        "defined",
        "available",
        "detail",
        "details",
        "needed",
        "need",
        "only",
        "explicit",
        "valid",
        "exact",
        "json",
        "yaml",
        "yml",
        "xml",
        "csv",
        "uri",
        "uris",
        "url",
        "urls",
        "string",
        "strings",
        "object",
        "objects",
        "record",
        "records",
        "manifest",
        "manifests",
    }
)


def is_actionability_advisory_concern(concern: dict, advisory_gaps: list[str]) -> bool:
    """Return whether an analyzer concern is covered by a non-blocking advisory gap.

    Analyzer concerns are filtered before document groups are counted. Version/build concerns are
    advisory only when each named product has its matching advisory evidence, and test-data
    format/example concerns can be advisory. Material API, RBAC, security, and operational
    concerns remain ordinary gaps. ``schema`` is material by default; an explicitly test-data-
    scoped schema is the one exception needed for fixture/payload descriptions.
    """
    text = " ".join(concern.get("text", "").split())
    if not text:
        return False

    normalized_advisories = {advisory.casefold() for advisory in advisory_gaps}
    has_version_advisory = any(label.casefold() in normalized_advisories for label in ACTIONABILITY_VERSION_LABELS)
    has_test_data_advisory = ACTIONABILITY_TEST_DATA_GAP.casefold() in normalized_advisories
    if not has_version_advisory and not has_test_data_advisory:
        return False
    if _OPERATOR_VERSION_REQUIREMENT_RE.search(text):
        return False

    required_version_advisories = {
        label.casefold() for label, pattern in _VERSION_PRODUCT_PATTERNS.items() if pattern.search(text)
    }
    if (
        has_version_advisory
        and _VERSION_ONLY_GAP_RE.search(text)
        and (not required_version_advisories or not required_version_advisories.issubset(normalized_advisories))
    ):
        return False

    material_terms = _MATERIAL_GAP_RE.findall(text)
    if material_terms:
        non_schema_terms = [term for term in material_terms if term.casefold() != "schema"]
        if (
            non_schema_terms
            or not _TEST_DATA_SCHEMA_CONTEXT_RE.search(text)
            or _MATERIAL_SCHEMA_CONTEXT_RE.search(text)
        ):
            return False

    words = re.findall(r"[a-z0-9]+", text.casefold())

    def uses_only(allowed_terms: frozenset[str]) -> bool:
        return bool(words) and all(
            word in allowed_terms or word.isdigit() or re.fullmatch(r"(?:v|ea|ga)\d+", word) for word in words
        )

    return bool(
        (has_version_advisory and _VERSION_ONLY_GAP_RE.search(text) and uses_only(_VERSION_ONLY_TERMS))
        or (has_test_data_advisory and _TEST_DATA_ONLY_GAP_RE.search(text) and uses_only(_TEST_DATA_ONLY_TERMS))
    )


def _extract_gaps_section(raw_text: str) -> str:
    """Extract the `## Gaps` section (case-insensitive) from a full analyzer document.

    Returns the lines after the first heading matching `## Gaps` (any case, e.g. `## GAPS`,
    `## gaps`) up to (but not including) the next level-2 (`##`) heading or EOF. `###`
    sub-headings do not terminate the section. If no such heading is found anywhere,
    returns raw_text unchanged (backward compat for bare gaps-only strings). If the
    heading IS present but yields no lines, returns empty string.
    """
    heading_line = next((line for line in raw_text.splitlines() if _GAPS_HEADING_RE.match(line)), None)
    if heading_line is None:
        # FAIL-OPEN: no "## Gaps" heading (case-insensitive) found at all.
        return raw_text
    lines, _ = extract_section(raw_text, heading_line)
    return "\n".join(lines)


def _clean_doc_type_token(raw: str) -> str:
    """Strip trailing punctuation and surrounding whitespace from a single doc-type token.

    Falls back to the pre-strip value if stripping would empty it, so an all-punctuation
    token (e.g. ".") never collapses to "".
    """
    cleaned = raw.strip()
    return cleaned.rstrip(".,;:").strip() or cleaned


def _normalize_doc_type(raw: str) -> str:
    """Normalize a raw resolved-by value to a canonical doc type or its own bucket key.

    Handles two LLM output quirks seen in practice, applied in order, so two analyzers
    citing the same primary document under different secondary wording still land in the
    same bucket instead of silently defeating the dedup this module exists for:

    1. Parenthetical elaboration on an otherwise-canonical answer (e.g.
       "feature refinement (PM/Engineering decision)" -> "feature refinement").
    2. A compound answer joining multiple doc types with "/" or " or " (e.g.
       "ADR / design doc") -> the first segment that matches a canonical type or
       synonym wins, regardless of position.

    Falls back to the cleaned-but-unrecognized string as its own bucket key if no segment
    matches (fail-open: an unrecognized doc type must never be silently dropped or split).
    """
    key = _clean_doc_type_token(_PARENTHETICAL_RE.sub("", raw))
    if canonical := _SYNONYMS.get(key.lower()):
        return canonical

    for segment in _COMPOUND_SEPARATOR_RE.split(key):
        segment_key = _clean_doc_type_token(segment)
        if segment_key and (canonical := _SYNONYMS.get(segment_key.lower())):
            return canonical

    return key


def _normalize_text(text: str) -> str:
    """Whitespace-normalize and lowercase for case-insensitive dedup comparison."""
    return " ".join(text.split()).lower()


def _coalesce_bullets(gaps_text: str) -> list[str]:
    """Coalesce physical lines into logical bullets.

    A logical bullet starts at a line whose stripped form starts with "- " and absorbs
    subsequent non-blank lines that do NOT start with "- " (joined with a single space);
    it terminates at a blank line, the next "- " line, or EOF. Standalone non-bullet lines
    (e.g. "No gaps identified.") never start a logical bullet and are ignored.
    """
    bullets = []
    current = None
    for line in gaps_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower() == "no gaps identified.":
            if current is not None:
                bullets.append(current)
                current = None
            continue
        if stripped.startswith("- "):
            if current is not None:
                bullets.append(current)
            current = stripped
        elif current is not None:
            current += " " + stripped
        # else: standalone non-bullet line outside any bullet — ignored.
    if current is not None:
        bullets.append(current)
    return bullets


def _parse_source(source_name: str, raw_text: str) -> list[dict]:
    """Parse one analyzer's raw ## Gaps markdown into a list of concern dicts.

    Each concern dict: {"text": str, "doc_type": str, "source": str}.
    Skips "No gaps identified." and blank lines. Bullets wrapped across multiple physical
    lines are coalesced into one logical bullet before matching. Malformed `- ` bullets (no
    "resolved by" clause) are kept under the "(unspecified)" doc type.
    """
    concerns = []
    gaps_text = _extract_gaps_section(raw_text)
    for bullet in _coalesce_bullets(gaps_text):
        if match := _BULLET_RE.match(bullet):
            doc_type = _normalize_doc_type(match.group("doc_type"))
            concerns.append({"text": match.group("desc").strip(), "doc_type": doc_type, "source": source_name})
        else:
            # Fail-open: a malformed bullet must never be silently dropped.
            desc_match = re.match(r"^-\s+\*\*(?P<desc>.+?)\*\*\s*", bullet)
            text = desc_match["desc"].strip() if desc_match else bullet[2:].strip()
            concerns.append({"text": text, "doc_type": UNSPECIFIED, "source": source_name})

    return concerns


def _doc_type_sort_key(doc_type: str):
    """Sort key: CANONICAL_DOC_TYPES order, then unrecognized alphabetically, then unspecified last."""
    if doc_type == UNSPECIFIED:
        return (2, "")
    if doc_type in CANONICAL_DOC_TYPES:
        return (0, CANONICAL_DOC_TYPES.index(doc_type))
    return (1, doc_type.lower())


def _render_body(feature_name: str, groups: list[dict]) -> str:
    """Render the flat-list markdown body from ordered groups."""
    header = f"# Gaps — {feature_name}"

    if not groups:
        return f"{header}\n\nNo gaps identified."

    lines = [header, ""]
    for group in groups:
        sources = ", ".join(_first_seen_sources(group["concerns"]))
        lines.append(f"- **{group['doc_type']}** — flagged by: {sources}")
        for concern in group["concerns"]:
            lines.append(f"  - {concern['text']}")

    return "\n".join(lines)


def _first_seen_sources(concerns: list[dict]) -> list[str]:
    """Union of source analyzers across concerns, in first-seen order."""
    seen = []
    for concern in concerns:
        for src in concern["sources"]:
            if src not in seen:
                seen.append(src)
    return seen


def consolidate_gaps(
    sources: dict[str, str], feature_name: str = "", *, concern_filter: Callable[[dict], bool] | None = None
) -> dict:
    """Consolidate raw ## Gaps markdown from multiple analyzers into deduplicated groups.

    Args:
        sources: maps analyzer name ("endpoints"|"risks"|"infra") -> raw ## Gaps markdown text.
        feature_name: feature name for the rendered body's `# Gaps — <Feature Name>` header.
            Optional for unit-testing the pure grouping logic; the CLI always supplies it.
        concern_filter: optional predicate applied to parsed concerns before grouping. A concern
            for which the predicate returns True is omitted from the consolidated groups. The
            default keeps every analyzer concern, including malformed bullets.

    Returns:
        {"gap_count": int, "status": "Open"|"Resolved", "body": <markdown flat list>,
         "groups": [{"doc_type": str, "concerns": [{"text": str, "sources": [str,...]}]}]}
    """
    # Preserve source order (endpoints, risks, infra) as given by the caller's dict.
    all_concerns = []
    for source_name, raw_text in sources.items():
        concerns = _parse_source(source_name, raw_text)
        if concern_filter is not None:
            concerns = [concern for concern in concerns if not concern_filter(concern)]
        all_concerns.extend(concerns)

    # Group by normalized doc type; within each group, dedup concern text
    # case-insensitively while keeping first-seen casing and order.
    groups_by_type: dict[str, list[dict]] = {}
    for concern in all_concerns:
        doc_type = concern["doc_type"]
        bucket = groups_by_type.setdefault(doc_type, [])

        normalized_text = _normalize_text(concern["text"])
        existing = next((c for c in bucket if _normalize_text(c["text"]) == normalized_text), None)
        if existing is None:
            bucket.append({"text": concern["text"], "sources": [concern["source"]]})
        elif concern["source"] not in existing["sources"]:
            existing["sources"].append(concern["source"])

    ordered_doc_types = sorted(groups_by_type.keys(), key=_doc_type_sort_key)
    groups = [{"doc_type": doc_type, "concerns": groups_by_type[doc_type]} for doc_type in ordered_doc_types]

    gap_count = len(groups)
    status = "Resolved" if gap_count == 0 else "Open"
    body = _render_body(feature_name, groups)

    return {
        "gap_count": gap_count,
        "status": status,
        "body": body,
        "groups": groups,
    }


def read_sources(source_args: list[str]) -> dict[str, str]:
    """Parse repeatable NAME=PATH --source args into {name: raw_text}.

    Raises ValueError with a stable error code (``invalid_source_argument`` or
    ``source_file_not_found``) on a malformed "NAME=PATH" argument or an unreadable
    source file. CLI entry points catch it and emit the shared JSON error contract.
    """
    sources = {}
    for entry in source_args:
        if "=" not in entry:
            raise ValueError("invalid_source_argument")
        name, path = entry.split("=", 1)
        try:
            with open(path, encoding="utf-8") as f:
                sources[name] = f.read()
        except OSError as e:
            raise ValueError("source_file_not_found") from e
    return sources

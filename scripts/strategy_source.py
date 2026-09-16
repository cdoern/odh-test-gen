"""Shared Jira issue-to-strategy formatting helpers.

This module contains the reusable strategy-source logic used by both the direct
``fetch_issue.py`` CLI and snapshot-first strategy resolution.
"""

import re
from typing import Any, Callable

from scripts.jira_utils import download_attachment

OVERFLOW_MARKER = "exceeds Jira's description size limit"
_FENCE_RE = re.compile(r"^[ \t]{0,3}(?P<fence>`{3,}|~{3,})(?P<rest>[^\r\n]*)")
AttachmentDownloader = Callable[[str], str]


def _attachment_sort_key(attachment: dict[str, Any]) -> tuple[Any, ...]:
    """Return the producer-compatible ordering key for an attachment."""
    attachment_id = str(attachment.get("id") or "")
    if attachment_id.isdigit():
        id_key = (1, int(attachment_id))
    else:
        id_key = (0, attachment_id)

    return (
        str(attachment.get("created") or ""),
        *id_key,
        str(attachment.get("content") or ""),
    )


def select_strategy_attachment(issue_key: str, attachments: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select the newest exact strategy attachment from an append-only Jira list.

    The ordering matches the strategy producer: ``created`` first, then numeric
    Jira IDs (preferred over nonnumeric IDs) or lexical nonnumeric IDs, and
    finally the content URL. Jira response order is intentionally ignored.
    """
    filename = f"{issue_key}-strategy.md"
    candidates = [attachment for attachment in attachments if attachment.get("filename") == filename]
    return max(candidates, key=_attachment_sort_key, default=None)


def _normalize_strategy_headings(strategy: str) -> str:
    """Convert unfenced Markdown level-2/3 headings to the parser's Jira-wiki form."""
    normalized = []
    active_fence: tuple[str, int] | None = None

    for line in strategy.splitlines(keepends=True):
        fence_match = _FENCE_RE.match(line)

        if active_fence is not None:
            normalized.append(line)
            if (
                fence_match
                and fence_match.group("fence")[0] == active_fence[0]
                and len(fence_match.group("fence")) >= active_fence[1]
                and not fence_match.group("rest").strip()
            ):
                active_fence = None
            continue

        if fence_match:
            normalized.append(line)
            fence = fence_match.group("fence")
            active_fence = (fence[0], len(fence))
            continue

        normalized.append(
            re.sub(
                r"^(###|##)([ \t]+)",
                lambda match: f"h{len(match.group(1))}.{match.group(2)}",
                line,
            )
        )

    return "".join(normalized)


def format_issue_as_markdown(
    issue_data: dict[str, Any], attachment_downloader: AttachmentDownloader | None = None
) -> str:
    """Format Jira issue data as Markdown.

    When Jira stores the full strategy in an attachment, the producer's
    overflow marker makes that exact newest strategy attachment authoritative.
    Matching attachments without the marker remain orphaned and are ignored.
    If the marker is present but no usable matching attachment is available, the
    fetched description is retained so the existing no-acceptance-criteria gate
    remains authoritative. Download errors are propagated to the caller.

    ``attachment_downloader`` is injectable so the direct CLI can preserve its
    existing module-level test seam while other callers use the Jira utility
    default.
    """
    fields = issue_data.get("fields", {})

    issue_key = issue_data.get("key", "UNKNOWN")
    summary = fields.get("summary", "No summary")
    description = fields.get("description", "No description provided")
    if description is None:
        description = "No description provided"
    issue_type = fields.get("issuetype", {}).get("name", "Unknown")
    status = fields.get("status", {}).get("name", "Unknown")
    labels = fields.get("labels", [])
    components = fields.get("components", [])

    if isinstance(description, str) and OVERFLOW_MARKER in description:
        attachment = select_strategy_attachment(issue_key, fields.get("attachment") or [])
        content_url = attachment.get("content") if attachment else None
        if content_url:
            downloader = attachment_downloader if attachment_downloader is not None else download_attachment
            description = _normalize_strategy_headings(downloader(content_url))

    lines = [
        f"# {issue_key}: {summary}",
        "",
        "## Metadata",
        "",
        f"- **Type**: {issue_type}",
        f"- **Status**: {status}",
    ]

    if labels:
        lines.append(f"- **Labels**: {', '.join(labels)}")

    if components:
        component_names = [c.get("name", "Unknown") for c in components]
        lines.append(f"- **Components**: {', '.join(component_names)}")

    lines.extend(
        [
            "",
            "## Description",
            "",
            description,
            "",
        ]
    )

    return "\n".join(lines)


def parse_components(markdown: str) -> list[str]:
    """Extract RHOAI product component names from formatted strategy Markdown."""
    section_match = re.search(r"^## Metadata\s*$(.*?)(?=\n## |\Z)", markdown, re.MULTILINE | re.DOTALL)
    if not section_match:
        return []

    match = re.search(r"^- \*\*Components\*\*: (.+)$", section_match.group(1), re.MULTILINE)
    if not match:
        return []
    return [name.strip() for name in match.group(1).split(",")]

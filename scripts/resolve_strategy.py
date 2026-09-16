#!/usr/bin/env python3
"""Resolve the source strategy for a feature, shared by test-plan-review and test-plan-score.

Snapshot-primary: reads the create-saved `<feature_dir>/.source-strategy.md` first; only
re-fetches from Jira (and saves it back, creating the feature directory if needed) when the
snapshot is missing. No degraded mode — a missing snapshot with a failed Jira fetch is a hard
failure.

Usage:
    uv run python scripts/resolve_strategy.py <feature_dir> <jira_key>
"""

import argparse
import json
import sys
from pathlib import Path

import requests

from scripts.jira_utils import AttachmentFetchError, get_issue
from scripts.strategy_source import format_issue_as_markdown
from scripts.utils.error_utils import exit_error_with_json
from scripts.utils.snapshot_io import write_snapshot_nofollow

SNAPSHOT_NAME = ".source-strategy.md"


def resolve_strategy(feature_dir: str, jira_key: str) -> dict:
    """Resolve the strategy, raising the real (typed) exception on a Jira fetch failure rather
    than stringifying it — the caller decides what's safe to surface (see main()'s
    jira_fetch_failed mapping, which avoids leaking request URLs/tokens/server data).
    """
    snapshot_path = Path(feature_dir) / SNAPSHOT_NAME

    # is_symlink() does NOT follow the link — it checks the entry itself.  A symlink here
    # (planted or substituted) must not be trusted as a snapshot hit: is_file() follows
    # symlinks and would return True for a symlink-to-regular-file, silently accepting a
    # redirected snapshot.  Reject outright so the write path (O_NOFOLLOW) runs and raises.
    if snapshot_path.is_symlink():
        raise OSError(f"snapshot path is a symlink (rejected for safety): {snapshot_path}")

    if snapshot_path.is_file():
        return {"status": "ok", "source": "snapshot", "strategy_file": str(snapshot_path)}

    issue_data = get_issue(jira_key)

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    write_snapshot_nofollow(snapshot_path, format_issue_as_markdown(issue_data))
    return {"status": "ok", "source": "refetch", "strategy_file": str(snapshot_path)}


def main():
    parser = argparse.ArgumentParser(description="Resolve the source strategy for a feature")
    parser.add_argument("feature_dir")
    parser.add_argument("jira_key")
    args = parser.parse_args()

    try:
        result = resolve_strategy(args.feature_dir, args.jira_key)
    except (requests.RequestException, AttachmentFetchError):
        exit_error_with_json({"status": "failed", "error": "jira_fetch_failed"})
    except OSError:
        exit_error_with_json({"status": "failed", "error": "snapshot_write_failed"})
    except Exception:
        exit_error_with_json({"status": "failed", "error": "strategy_resolution_failed"})

    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()

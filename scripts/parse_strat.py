#!/usr/bin/env python3
"""Parse sections from fetched STRAT content (Jira wiki markup).

Extracts acceptance criteria, non-functional requirements, and
out-of-scope items from the output of fetch_issue.py.

Usage:
    uv run python scripts/parse_strat.py acceptance-criteria <strat_file>
    uv run python scripts/parse_strat.py nfr <strat_file>
    uv run python scripts/parse_strat.py out-of-scope <strat_file>
    uv run python scripts/parse_strat.py workflow-inputs <strat_file>
    uv run python scripts/parse_strat.py resolve-local <jira_key>
    uv run python scripts/parse_strat.py new-strat-tmp
    uv run python scripts/parse_strat.py save-snapshot <strategy_file> <feature_dir>
"""

import argparse
import contextlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

from scripts.strategy_source import parse_components
from scripts.utils.error_utils import exit_error_with_json
from scripts.utils.repo_utils import get_git_root
from scripts.utils.schemas import SCHEMAS
from scripts.utils.snapshot_io import read_file_nofollow, write_snapshot_nofollow
from scripts.utils.strat_utils import parse_acceptance_criteria, parse_nfr, parse_out_of_scope, workflow_inputs

JIRA_KEY_RE = re.compile(SCHEMAS["test-plan"]["source_key"]["pattern"])


OUTPUT_DIR_MARKER = ".test-plan-output-dir.json"


def _permitted_strat_path(raw_path: str) -> Path:
    """Resolve raw_path and confirm it sits inside a permitted location, shared by every
    subcommand that touches a strategy file on disk.

    Permitted locations:
    - `<repo_root>/artifacts/strat-tasks/<KEY>.md` — persistent local cache
    - `<repo_root>/artifacts/strat-tasks/.tmp/` — ephemeral fetch (mode-0700, never shared system temp)
    - Output dir from `<feature_dir>/.test-plan-output-dir.json` (written by save-snapshot)

    Anything else is rejected so a malformed or malicious strat_file argument can't be used to
    read or move arbitrary files.
    """
    resolved = Path(raw_path).resolve()
    repo_root = get_git_root(str(Path(__file__).resolve().parent))
    if not repo_root:
        raise ValueError("strategy_file_not_permitted")

    strat_root = (Path(repo_root) / "artifacts" / "strat-tasks").resolve()
    allowed_roots = [strat_root, strat_root / ".tmp"]

    # For snapshots like <output_dir>/<feature_name>/.source-strategy.md,
    # the parent is the feature dir — read .test-plan-output-dir.json from there
    feature_dir = resolved.parent
    marker = feature_dir / OUTPUT_DIR_MARKER
    if marker.is_file() and not marker.is_symlink():
        with contextlib.suppress(json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
            data = json.loads(marker.read_text())
            # Validate marker shape: must be dict with string output_dir pointing to existing dir
            if isinstance(data, dict) and isinstance(data.get("output_dir"), str):
                output_dir_path = Path(data["output_dir"]).resolve()
                if output_dir_path.is_dir():
                    allowed_roots.append(output_dir_path)

    if not any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots):
        raise ValueError("strategy_file_not_permitted")

    return resolved


def _load_strat_content(raw_path: str) -> str:
    """Read strat_file after confirming it resolves inside a permitted location (see
    _permitted_strat_path)."""
    resolved = _permitted_strat_path(raw_path)
    return read_file_nofollow(resolved)


def _write_snapshot(snapshot_path: Path, content: str) -> None:
    """Write content to snapshot_path without ever following a symlink there.

    Delegates to write_snapshot_nofollow (O_NOFOLLOW rejects a planted/substituted symlink at
    open time instead of silently writing through it; O_TRUNC still allows overwriting a real
    pre-existing snapshot on re-run).
    """
    write_snapshot_nofollow(snapshot_path, content)


def save_snapshot(strategy_file: str, feature_dir: str) -> dict:
    """Persist a fetched/cached strategy file as <feature_dir>/.source-strategy.md and extract
    its RHOAI components in the same call.

    Also writes <feature_dir>/.test-plan-output-dir.json (output_dir = feature_dir's parent)
    so that _permitted_strat_path and other skills can discover the output directory without
    relying on the TEST_PLAN_OUTPUT_DIR environment variable.

    A file under the ephemeral artifacts/strat-tasks/.tmp/ scratch dir is deleted after (nothing
    else references it); a file directly under artifacts/strat-tasks/ is the shared cache other
    skills fall back to, so it is left in place.
    """
    resolved = _permitted_strat_path(strategy_file)
    repo_root = get_git_root(str(Path(__file__).resolve().parent))
    tmp_root = (Path(repo_root) / "artifacts" / "strat-tasks" / ".tmp").resolve()

    feature_path = Path(feature_dir)
    feature_path.mkdir(parents=True, exist_ok=True)
    snapshot_path = feature_path / ".source-strategy.md"

    # Read via _load_strat_content (not a raw rename/copy of `resolved`): its O_NOFOLLOW open
    # closes the gap between the containment check above and this read — if the source path was
    # substituted for a symlink in between, the kernel rejects it instead of following it
    # wherever it points.
    content = _load_strat_content(str(resolved))
    _write_snapshot(snapshot_path, content)

    # Persist output dir so scripts/skills can find it without env vars.
    # Same O_NOFOLLOW writer as the snapshot: a planted symlink at the marker
    # must not redirect this write.
    marker_path = feature_path / OUTPUT_DIR_MARKER
    _write_snapshot(marker_path, json.dumps({"output_dir": str(feature_path.parent.resolve())}) + "\n")

    if resolved.is_relative_to(tmp_root):
        resolved.unlink()
        source = "temp"
    else:
        source = "cache"

    components = parse_components(content)

    return {"status": "ok", "strategy_file": str(snapshot_path), "source": source, "components": components}


def cmd_acceptance_criteria(args):
    try:
        content = _load_strat_content(args.strat_file)
    except (ValueError, OSError):
        exit_error_with_json({"status": "error", "error": "strategy_file_unreadable"})
    result = parse_acceptance_criteria(content)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["found"] and result["count"] > 0 else 1)


def cmd_nfr(args):
    try:
        content = _load_strat_content(args.strat_file)
    except (ValueError, OSError):
        exit_error_with_json({"status": "error", "error": "strategy_file_unreadable"})
    result = parse_nfr(content)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["found"] else 1)


def cmd_out_of_scope(args):
    try:
        content = _load_strat_content(args.strat_file)
    except (ValueError, OSError):
        exit_error_with_json({"status": "error", "error": "strategy_file_unreadable"})
    result = parse_out_of_scope(content)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["found"] else 1)


def cmd_resolve_local(args):
    if not JIRA_KEY_RE.match(args.jira_key):
        exit_error_with_json({"found": False, "error": "malformed_jira_key"})

    repo_root = get_git_root(str(Path(__file__).resolve().parent))
    if not repo_root:
        exit_error_with_json({"found": False, "error": "repo_root_not_found"})

    strat_dir = (Path(repo_root) / "artifacts" / "strat-tasks").resolve()
    candidate = (strat_dir / f"{args.jira_key}.md").resolve()

    if not candidate.is_file() or not (candidate == strat_dir or candidate.is_relative_to(strat_dir)):
        exit_error_with_json({"found": False, "error": "strategy_file_not_found"})

    print(json.dumps({"found": True, "strategy_file": str(candidate)}, indent=2))
    sys.exit(0)


def cmd_new_strat_tmp(args):
    """Create a fresh, unguessably-named file inside the owned artifacts/strat-tasks/.tmp/
    directory (mode 0700, created/enforced on every call) for an ephemeral Jira fetch — replaces
    bare `mktemp`, which would land in the shared system temp dir that _load_strat_content no
    longer trusts.

    Uses descriptor-relative operations (O_NOFOLLOW + dir_fd) throughout instead of re-resolving
    ".tmp" as a path string at each step: a path-based `mkdir(exist_ok=True)` silently accepts a
    pre-existing symlink at ".tmp" (it only checks that the resolved target is a directory), and a
    plain `os.chmod`/`tempfile.mkstemp(dir=...)` would then follow that symlink — retargeting the
    mode change and the new file onto whatever directory the symlink points at (CWE-59/CWE-367).
    Opening the parent with O_NOFOLLOW and operating on its descriptor for every subsequent step
    means a symlink at ".tmp" is rejected outright rather than silently followed.
    """
    repo_root = get_git_root(str(Path(__file__).resolve().parent))
    if not repo_root:
        exit_error_with_json({"created": False, "error": "repo_root_not_found"})

    strat_root = Path(repo_root) / "artifacts" / "strat-tasks"
    strat_root.mkdir(parents=True, exist_ok=True)

    try:
        root_fd = os.open(strat_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with contextlib.suppress(FileExistsError):
                os.mkdir(".tmp", 0o700, dir_fd=root_fd)
            tmp_fd = os.open(".tmp", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        finally:
            os.close(root_fd)

        try:
            os.fchmod(tmp_fd, 0o700)
            for _ in range(10):
                name = f"strategy.{secrets.token_hex(8)}.md"
                try:
                    file_fd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600, dir_fd=tmp_fd)
                    os.close(file_fd)
                    break
                except FileExistsError:
                    continue
            else:
                raise OSError("failed to create a unique strategy temp file")
        finally:
            os.close(tmp_fd)
    except OSError:
        exit_error_with_json({"created": False, "error": "strategy_tmp_unavailable"})

    path = str(strat_root / ".tmp" / name)
    print(json.dumps({"created": True, "strategy_file": path}, indent=2))
    sys.exit(0)


def cmd_save_snapshot(args):
    try:
        result = save_snapshot(args.strategy_file, args.feature_dir)
    except ValueError:
        exit_error_with_json({"status": "error", "error": "strategy_file_not_permitted"})
    except OSError:
        exit_error_with_json({"status": "error", "error": "snapshot_write_unsafe"})

    print(json.dumps(result, indent=2))
    sys.exit(0)


def cmd_workflow_inputs(args):
    try:
        content = _load_strat_content(args.strat_file)
    except (ValueError, OSError):
        exit_error_with_json({"status": "error", "error": "strategy_file_unreadable"})

    result = workflow_inputs(content)
    print(json.dumps(result, indent=2))
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description="Parse sections from fetched STRAT content",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_ac = subparsers.add_parser("acceptance-criteria", help="Extract acceptance criteria")
    p_ac.add_argument("strat_file", help="Path to fetched STRAT markdown file")
    p_ac.set_defaults(func=cmd_acceptance_criteria)

    p_nfr = subparsers.add_parser("nfr", help="Extract non-functional requirements")
    p_nfr.add_argument("strat_file", help="Path to fetched STRAT markdown file")
    p_nfr.set_defaults(func=cmd_nfr)

    p_oos = subparsers.add_parser("out-of-scope", help="Extract out-of-scope items")
    p_oos.add_argument("strat_file", help="Path to fetched STRAT markdown file")
    p_oos.set_defaults(func=cmd_out_of_scope)

    p_workflow = subparsers.add_parser(
        "workflow-inputs",
        help="Combined ac/nfr/out-of-scope parse + gate inputs for test-plan-create Step 1.5",
    )
    p_workflow.add_argument("strat_file", help="Path to fetched STRAT markdown file")
    p_workflow.set_defaults(func=cmd_workflow_inputs)

    p_resolve = subparsers.add_parser(
        "resolve-local", help="Validate a Jira key and resolve it to a cached artifacts/strat-tasks/ file"
    )
    p_resolve.add_argument("jira_key", help="Jira key, e.g. RHAISTRAT-1746")
    p_resolve.set_defaults(func=cmd_resolve_local)

    p_new_tmp = subparsers.add_parser(
        "new-strat-tmp", help="Create a fresh ephemeral strategy file inside the owned .tmp/ cache dir"
    )
    p_new_tmp.set_defaults(func=cmd_new_strat_tmp)

    p_save_snapshot = subparsers.add_parser(
        "save-snapshot", help="Persist a fetched/cached strategy file as <feature_dir>/.source-strategy.md"
    )
    p_save_snapshot.add_argument("strategy_file", help="Path to fetched STRAT markdown file (temp or cache)")
    p_save_snapshot.add_argument("feature_dir", help="Feature directory to snapshot into")
    p_save_snapshot.set_defaults(func=cmd_save_snapshot)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

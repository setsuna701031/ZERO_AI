from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.tools.approval_record import list_outbox_artifacts, write_approval_record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run approval for github_outbox artifacts. Does not commit, push, call GitHub, or create PRs."
    )
    parser.add_argument("--workspace", default=".", help="Repository root, default: current directory")
    parser.add_argument("--task", default="", help="Optional task id to store under replay_source")
    parser.add_argument("--trace", default="", help="Optional trace path to store under replay_source")
    parser.add_argument(
        "--decision",
        choices=["yes", "no", "approved", "rejected"],
        default="",
        help="Non-interactive decision for tests or automation",
    )
    args = parser.parse_args()

    workspace_root = Path(args.workspace).resolve(strict=False)
    listed = list_outbox_artifacts(workspace_root=workspace_root)
    if not listed.get("ok"):
        print(f"ERROR: {listed.get('error')}")
        return 1

    print("GitHub Outbox Approval (dry-run)")
    print("No commit, push, GitHub API call, or PR creation will be executed.")
    print("")
    print("Artifacts:")
    for item in listed.get("artifacts", []):
        exists = "exists" if item.get("exists") else "missing"
        size = f"{item.get('size_bytes')}B" if item.get("size_bytes") is not None else "unknown"
        sha = item.get("sha256_12") or "-"
        print(f"- {item.get('name')} (size: {size}, sha256: {sha}, {exists})")
        if item.get("exists"):
            print("")
            print(_preview_file(Path(item.get("full_path") or ""), max_chars=1800))
            print("")

    missing = listed.get("missing") or []
    if missing:
        print(f"ERROR: missing required artifacts: {', '.join(missing)}")
        return 1

    decision = str(args.decision or "").strip().lower()
    if not decision:
        decision = input("Approve these exact artifacts? [yes/no]: ").strip().lower()

    if decision in {"yes", "y", "approved", "approve"}:
        normalized = "approved"
    elif decision in {"no", "n", "rejected", "reject"}:
        normalized = "rejected"
    else:
        print("ERROR: decision must be yes or no")
        return 1

    result = write_approval_record(
        decision=normalized,
        workspace_root=workspace_root,
        task_id=args.task,
        trace_path=args.trace,
        source="approve_outbox_cli",
    )
    if not result.get("ok"):
        print(f"ERROR: {result.get('error')}")
        return 1

    print("")
    print(f"Decision: {result.get('decision')}")
    print(f"Record: {result.get('record_logical_path')}")
    print("Safety: git_commit=false git_push=false github_create_pr=false mutation_attempt=0")
    return 0


def _preview_file(path: Path, *, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return f"[preview unavailable: {exc}]"
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


if __name__ == "__main__":
    raise SystemExit(main())

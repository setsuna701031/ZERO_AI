from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show a dry-run execution plan from an approval record. This script never mutates git, GitHub, or the repo."
    )
    parser.add_argument("--approval", required=True, help="Path to approval_record.json")
    args = parser.parse_args()

    approval_path = Path(args.approval).resolve(strict=False)
    if not approval_path.exists():
        print("[DRY-RUN EXECUTION PLAN]")
        print("")
        print("Blocked:")
        print(f"- approval file not found: {approval_path}")
        print("")
        print("Safety:")
        print("- no commit")
        print("- no push")
        print("- no GitHub API call")
        print("- no repo changes")
        return 1

    record, read_error = _read_json(approval_path)
    if not isinstance(record, dict):
        print("[DRY-RUN EXECUTION PLAN]")
        print("")
        print("Blocked:")
        print(f"- failed to read approval record: {read_error or 'invalid JSON object'}")
        print("")
        print("Safety:")
        print("- no commit")
        print("- no push")
        print("- no GitHub API call")
        print("- no repo changes")
        return 1

    approved = record.get("approved") is True and str(record.get("decision") or "").lower() == "approved"
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), list) else []
    commit_artifact = _find_artifact(artifacts, "commit_message.txt")
    pr_artifact = _find_artifact(artifacts, "pr_description.md")

    print("[DRY-RUN EXECUTION PLAN]")
    print("")
    print("Would execute:")
    print(f"- git add {commit_artifact.get('path') or 'workspace/github_outbox/commit_message.txt'}")
    print("- git commit -m <commit message from approved artifact>")
    print("- git push")
    print("- create PR from approved pr_description.md")
    print("")
    print("Blocked:")
    print("- External mutation disabled (dry-run mode)")
    if not approved:
        print("- Approval record is not approved")
    print("")
    print("Source:")
    print(f"- {approval_path.name} ({'approved' if approved else 'not approved'})")
    print("")
    print("Artifacts:")
    for item in artifacts:
        name = item.get("name") or "unknown"
        size = f"{item.get('size_bytes')}B" if item.get("size_bytes") is not None else "unknown"
        sha = item.get("sha256_12") or "-"
        print(f"- {name} (size: {size}, sha256: {sha})")
    if pr_artifact:
        _ = pr_artifact
    print("")
    print("Safety:")
    print("- no commit")
    print("- no push")
    print("- no GitHub API call")
    print("- no repo changes")
    return 0 if approved else 1


def _read_json(path: Path) -> tuple[Any, str]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle), ""
    except Exception as exc:
        return None, str(exc)


def _find_artifact(artifacts: List[Any], name: str) -> Dict[str, Any]:
    for item in artifacts:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return {}


if __name__ == "__main__":
    raise SystemExit(main())

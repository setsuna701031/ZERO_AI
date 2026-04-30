from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_COMMIT_TITLE = "Apply approved GitHub outbox artifacts"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preview a policy-controlled execution plan from an approval record. "
            "This script never executes git commands, never calls GitHub, and never changes remotes."
        )
    )
    parser.add_argument("--approval", required=True, help="Path to approval_record.json")
    parser.add_argument(
        "--policy-preview",
        action="store_true",
        help="Required guard flag. Shows the policy preview only; no execution is performed.",
    )
    parser.add_argument("--repo", default=".", help="Repository root, default: current directory")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve(strict=False)
    approval_path = Path(args.approval)
    if not approval_path.is_absolute():
        approval_path = repo_root / approval_path
    approval_path = approval_path.resolve(strict=False)

    record, error = _load_record(approval_path)
    if not isinstance(record, dict):
        _print_header()
        print("Blocked:")
        print(f"- failed to read approval record: {error}")
        _print_safety()
        return 1

    approved = record.get("approved") is True and str(record.get("decision") or "").lower() == "approved"
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), list) else []
    commit_artifact = _find_artifact(artifacts, "commit_message.txt")
    pr_artifact = _find_artifact(artifacts, "pr_description.md")
    paths = _approved_local_paths([commit_artifact, pr_artifact], repo_root=repo_root)
    commit_message = _commit_message_from_artifact(commit_artifact, repo_root=repo_root)

    _print_header()
    _print_policy()
    _print_source_and_artifacts(approval_path=approval_path, approved=approved, artifacts=artifacts)

    if not args.policy_preview:
        print("Blocked:")
        print("- policy preview flag required: --policy-preview")
        print("- actual local git execution disabled")
        _print_safety()
        return 1

    if not approved:
        print("Blocked:")
        print("- Approval record is not approved")
        print("- actual local git execution disabled")
        _print_safety()
        return 1

    if not paths:
        print("Blocked:")
        print("- No approved local outbox artifact paths found")
        print("- actual local git execution disabled")
        _print_safety()
        return 1

    print("Execution mode: PLAN ONLY")
    print("")
    print("Would execute:")
    for path in paths:
        print(f"- git add {path.as_posix()}")
    print(f"- git commit -m {json.dumps(commit_message)}")
    print("")
    print("Blocked:")
    print("- actual local git execution disabled")
    print("- git push")
    print("- create PR")
    print("- remote operation")
    _print_safety()
    return 0


def _load_record(path: Path) -> tuple[Any, str]:
    if not path.exists():
        return None, f"approval file not found: {path}"
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle), ""
    except Exception as exc:
        return None, str(exc)


def _approved_local_paths(artifacts: List[Dict[str, Any]], *, repo_root: Path) -> List[Path]:
    allowed = {
        "workspace/github_outbox/commit_message.txt",
        "workspace/github_outbox/pr_description.md",
    }
    paths: List[Path] = []
    for item in artifacts:
        raw = str(item.get("path") or "").strip()
        if not raw:
            continue
        path = Path(raw)
        candidate = path.resolve(strict=False) if path.is_absolute() else (repo_root / path).resolve(strict=False)
        if not _is_relative_to(candidate, repo_root):
            continue
        relative = candidate.relative_to(repo_root)
        if relative.as_posix() in allowed:
            paths.append(relative)
    return paths


def _commit_message_from_artifact(artifact: Dict[str, Any], *, repo_root: Path) -> str:
    raw = str(artifact.get("path") or "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = repo_root / path
        try:
            text = path.read_text(encoding="utf-8-sig").strip()
            first_line = text.splitlines()[0].strip()
            if first_line:
                return first_line[:120]
        except Exception:
            pass
    return DEFAULT_COMMIT_TITLE


def _find_artifact(artifacts: List[Any], name: str) -> Dict[str, Any]:
    for item in artifacts:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return {}


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(base.resolve(strict=False))
        return True
    except ValueError:
        return False


def _print_header() -> None:
    print("[POLICY-CONTROLLED EXECUTION]")
    print("")


def _print_policy() -> None:
    print("Policy:")
    print("allow:")
    print("- local git add")
    print("- local git commit")
    print("")
    print("deny:")
    print("- push")
    print("- PR")
    print("- remote")
    print("")


def _print_source_and_artifacts(*, approval_path: Path, approved: bool, artifacts: List[Any]) -> None:
    print("Source:")
    print(f"- {approval_path.name} ({'approved' if approved else 'not approved'})")
    print("")
    print("Artifacts:")
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "unknown"
        size = f"{item.get('size_bytes')}B" if item.get("size_bytes") is not None else "unknown"
        sha = item.get("sha256_12") or "-"
        print(f"- {name} (size: {size}, sha256: {sha})")
    print("")


def _print_safety() -> None:
    print("")
    print("Safety:")
    print("- no commit")
    print("- no push")
    print("- no GitHub API call")
    print("- no remote changes")


if __name__ == "__main__":
    raise SystemExit(main())

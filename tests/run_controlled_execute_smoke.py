from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def fail(message: str) -> int:
    print(f"[controlled-execute-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[controlled-execute-smoke] PASS: {message}")


def write_record(path: Path, *, approved: bool) -> None:
    decision = "approved" if approved else "rejected"
    payload = {
        "schema": "approval_record.v1",
        "source": "approve_outbox_cli",
        "decision": decision,
        "approved": approved,
        "artifacts": [
            {
                "name": "commit_message.txt",
                "path": "workspace/github_outbox/commit_message.txt",
                "size_bytes": 38,
                "sha256_12": "73363d89136a",
            },
            {
                "name": "pr_description.md",
                "path": "workspace/github_outbox/pr_description.md",
                "size_bytes": 27,
                "sha256_12": "de4af704d931",
            },
        ],
        "safety": {
            "git_commit": False,
            "git_push": False,
            "github_create_pr": False,
            "mutation_attempt": 0,
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_controlled_execute(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(REPO_ROOT / "controlled_execute.py"), "--approval", str(path)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def assert_no_real_mutation_text(output: str) -> None:
    required = [
        "[DRY-RUN EXECUTION PLAN]",
        "Would execute:",
        "- git add workspace/github_outbox/commit_message.txt",
        "- git commit -m <commit message from approved artifact>",
        "- git push",
        "- create PR from approved pr_description.md",
        "Blocked:",
        "- External mutation disabled (dry-run mode)",
        "Safety:",
        "- no commit",
        "- no push",
        "- no GitHub API call",
        "- no repo changes",
    ]
    for item in required:
        if item not in output:
            raise AssertionError(f"missing output text: {item}\n{output}")


def main() -> int:
    print("[controlled-execute-smoke] START")

    tmp_dir = REPO_ROOT / ".codex_tmp" / "controlled_execute_smoke"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    approved_path = tmp_dir / "approval_record.json"
    rejected_path = tmp_dir / "rejection_record.json"

    write_record(approved_path, approved=True)
    approved = run_controlled_execute(approved_path)
    print(approved.stdout)
    if approved.returncode != 0:
        return fail(f"approved record should exit 0, got {approved.returncode}: {approved.stderr}")
    try:
        assert_no_real_mutation_text(approved.stdout)
    except AssertionError as exc:
        return fail(str(exc))
    if "approval_record.json (approved)" not in approved.stdout:
        return fail("approved source line missing")
    if "sha256: 73363d89136a" not in approved.stdout or "sha256: de4af704d931" not in approved.stdout:
        return fail("artifact hashes missing from approved output")
    pass_step("approved record shows dry-run plan only")

    write_record(rejected_path, approved=False)
    rejected = run_controlled_execute(rejected_path)
    print(rejected.stdout)
    if rejected.returncode != 1:
        return fail(f"rejected record should exit 1, got {rejected.returncode}: {rejected.stderr}")
    try:
        assert_no_real_mutation_text(rejected.stdout)
    except AssertionError as exc:
        return fail(str(exc))
    if "- Approval record is not approved" not in rejected.stdout:
        return fail("rejected blocked reason missing")
    if "rejection_record.json (not approved)" not in rejected.stdout:
        return fail("rejected source line missing")
    pass_step("rejected record is blocked with exit code 1")

    print("[controlled-execute-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

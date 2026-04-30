from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
OUTBOX = REPO_ROOT / "workspace" / "github_outbox"
OUTBOX_ARTIFACTS = (
    OUTBOX / "commit_message.txt",
    OUTBOX / "pr_description.md",
    OUTBOX / "approval_record.json",
    OUTBOX / "rejection_record.json",
)


def fail(message: str) -> int:
    print(f"[approval-record-smoke] FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"[approval-record-smoke] PASS: {message}")


def write_outbox_fixture() -> None:
    OUTBOX.mkdir(parents=True, exist_ok=True)
    (OUTBOX / "commit_message.txt").write_text("Update approval layer\n\n- Add dry-run records", encoding="utf-8")
    (OUTBOX / "pr_description.md").write_text(
        "## Summary\n- Add approval and rejection audit records\n\n## Safety\n- No GitHub mutation",
        encoding="utf-8",
    )


def snapshot_files(paths: tuple[Path, ...]) -> dict[Path, str | None]:
    snapshot: dict[Path, str | None] = {}
    for path in paths:
        if not path.exists():
            snapshot[path] = None
            continue
        content = path.read_text(encoding="utf-8")
        if path.name in {"approval_record.json", "rejection_record.json"}:
            try:
                data = json.loads(content)
            except Exception:
                data = {}
            replay_source = data.get("replay_source") if isinstance(data, dict) else {}
            if isinstance(replay_source, dict) and replay_source.get("task_id") == "task_approval_record_smoke":
                snapshot[path] = None
                continue
        snapshot[path] = content
    return snapshot


def restore_files(snapshot: dict[Path, str | None]) -> None:
    for path, content in snapshot.items():
        if content is None:
            if path.exists():
                path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def run_approve(decision: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            PYTHON,
            str(REPO_ROOT / "approve_outbox.py"),
            "--decision",
            decision,
            "--task",
            "task_approval_record_smoke",
            "--trace",
            "workspace/tasks/task_approval_record_smoke/trace.json",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_record(path: Path, *, decision: str, approved: bool) -> None:
    if not path.exists():
        raise AssertionError(f"record missing: {path}")
    record = load_json(path)
    if record.get("schema") != "approval_record.v1":
        raise AssertionError(f"schema mismatch: {record}")
    if record.get("source") != "approve_outbox_cli":
        raise AssertionError(f"source mismatch: {record}")
    if record.get("decision") != decision or record.get("approved") is not approved:
        raise AssertionError(f"decision mismatch: {record}")
    replay_source = record.get("replay_source")
    if not isinstance(replay_source, dict):
        raise AssertionError(f"replay_source missing: {record}")
    for key in ("task_id", "trace_path", "outbox_dir"):
        if key not in replay_source:
            raise AssertionError(f"replay_source.{key} missing: {record}")
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise AssertionError(f"artifacts mismatch: {record}")
    for item in artifacts:
        if not item.get("name") or not item.get("path"):
            raise AssertionError(f"artifact identity missing: {item}")
        if item.get("size_bytes") is None or not item.get("sha256_12"):
            raise AssertionError(f"artifact hash/size missing: {item}")
    safety = record.get("safety")
    if not isinstance(safety, dict):
        raise AssertionError(f"safety missing: {record}")
    if safety.get("git_commit") or safety.get("git_push") or safety.get("github_create_pr"):
        raise AssertionError(f"mutation flag set: {record}")
    if safety.get("mutation_attempt") != 0:
        raise AssertionError(f"mutation_attempt mismatch: {record}")
    text = json.dumps(record, ensure_ascii=False).lower()
    blocked = ["github_token", "api.github.com", "remote_url", "access_token"]
    if any(token in text for token in blocked):
        raise AssertionError(f"record leaked forbidden token/url fields: {record}")


def main() -> int:
    print("[approval-record-smoke] START")
    snapshot = snapshot_files(OUTBOX_ARTIFACTS)
    try:
        write_outbox_fixture()
        pass_step("outbox fixture written")

        yes = run_approve("yes")
        print(yes.stdout)
        if yes.returncode != 0:
            return fail(f"yes approval failed: {yes.stderr}")
        for expected in (
            "GitHub Outbox Approval (dry-run)",
            "commit_message.txt (size: 46B, sha256: 7f936a921362, exists)",
            "pr_description.md (size: 89B, sha256: dc206ec491d8, exists)",
            "Decision: approved",
            "Safety: git_commit=false git_push=false github_create_pr=false mutation_attempt=0",
        ):
            if expected not in yes.stdout:
                return fail(f"yes output missing: {expected}")
        try:
            assert_record(OUTBOX / "approval_record.json", decision="approved", approved=True)
        except AssertionError as exc:
            return fail(str(exc))
        pass_step("yes writes approval_record.json with replay source, artifact hashes, and safety flags")

        no = run_approve("no")
        print(no.stdout)
        if no.returncode != 0:
            return fail(f"no rejection failed: {no.stderr}")
        if "Decision: rejected" not in no.stdout:
            return fail("no output missing rejected decision")
        try:
            assert_record(OUTBOX / "rejection_record.json", decision="rejected", approved=False)
        except AssertionError as exc:
            return fail(str(exc))
        pass_step("no writes rejection_record.json for audit continuity")

        approval = load_json(OUTBOX / "approval_record.json")
        rejection = load_json(OUTBOX / "rejection_record.json")
        if approval.get("safety", {}).get("git_commit") or rejection.get("safety", {}).get("github_create_pr"):
            return fail("approval records reported git/GitHub mutation")
        pass_step("approval layer does not commit, push, or create PR")
    finally:
        restore_files(snapshot)

    print("[approval-record-smoke] ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

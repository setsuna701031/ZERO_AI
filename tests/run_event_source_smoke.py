from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.events.event_runner import EventRunner


PREFIX = "[event-source-smoke]"
EVENTS_INBOX = REPO_ROOT / "workspace" / "events_inbox"
EVENTS_OUTBOX = REPO_ROOT / "workspace" / "events_outbox"
EVENT_RESULTS = EVENTS_OUTBOX / "event_results.jsonl"
SESSIONS = REPO_ROOT / "workspace" / "execution_sessions"
AUDIT_LOG = REPO_ROOT / "workspace" / "audit_logs" / "tool_audit.jsonl"


def fail(message: str) -> int:
    print(f"{PREFIX} FAIL: {message}")
    return 1


def pass_step(message: str) -> None:
    print(f"{PREFIX} PASS: {message}")


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()])


def session_files() -> set[Path]:
    if not SESSIONS.exists():
        return set()
    return set(SESSIONS.glob("*.json"))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def main() -> int:
    EVENTS_INBOX.mkdir(parents=True, exist_ok=True)
    EVENTS_OUTBOX.mkdir(parents=True, exist_ok=True)
    (EVENTS_INBOX / ".gitkeep").touch()
    (EVENTS_OUTBOX / ".gitkeep").touch()

    event_file = EVENTS_INBOX / "issue_event.txt"
    event_file.write_text("Issue: review/analyze this local file event.\n", encoding="utf-8")

    before_results = line_count(EVENT_RESULTS)
    before_sessions = session_files()
    before_audit = line_count(AUDIT_LOG)

    records = EventRunner(repo_root=str(REPO_ROOT)).poll_once()
    if not records:
        return fail("poll_once returned no event result records")
    pass_step("poll_once returned event result records")

    matching_records = [
        record for record in records
        if record.get("event", {}).get("path", "").endswith("issue_event.txt")
    ]
    if not matching_records:
        return fail(f"no EventRecord for issue_event.txt: {records}")
    if not matching_records[0].get("event", {}).get("event_id"):
        return fail(f"EventRecord missing event_id: {matching_records[0]}")
    pass_step("EventRecord created for issue_event.txt")

    task = matching_records[0].get("task", {})
    if task.get("type") != "github_inbox" or "review/analyze file event" not in str(task.get("title")):
        return fail(f"event was not converted to expected task: {task}")
    pass_step("event converted to github_inbox task")

    after_results = line_count(EVENT_RESULTS)
    if after_results <= before_results:
        return fail(f"event_results.jsonl did not grow: before={before_results}, after={after_results}")

    result_records = read_jsonl(EVENT_RESULTS)
    if not result_records:
        return fail(f"event_results.jsonl missing records: {EVENT_RESULTS}")
    if not any(record.get("event", {}).get("path", "").endswith("issue_event.txt") for record in result_records):
        return fail(f"event_results.jsonl missing issue_event.txt record: {EVENT_RESULTS}")
    pass_step(f"event result written to {EVENT_RESULTS}")

    created_sessions = session_files() - before_sessions
    if not created_sessions:
        return fail(f"no execution session json created in {SESSIONS}")
    pass_step("execution session json created")

    after_audit = line_count(AUDIT_LOG)
    if after_audit <= before_audit:
        return fail(f"audit log did not grow: before={before_audit}, after={after_audit}")
    pass_step("audit log appended")

    forbidden = matching_records[0].get("forbidden_mutations", {})
    if forbidden.get("git_commit") or forbidden.get("git_push") or forbidden.get("github_create_pr"):
        return fail(f"forbidden mutation attempted: {matching_records[0]}")
    pass_step("no GitHub API, commit, or push was attempted")

    print(f"{PREFIX} ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

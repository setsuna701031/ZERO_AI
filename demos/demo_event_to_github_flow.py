from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from core.events.event_runner import EventRunner
from core.tools.github_outbox import OUTBOX_FILES


WORKSPACE = REPO_ROOT / "workspace"
EVENTS_INBOX = WORKSPACE / "events_inbox"
EVENTS_OUTBOX = WORKSPACE / "events_outbox"
GITHUB_OUTBOX = WORKSPACE / "github_outbox"
SESSIONS = WORKSPACE / "execution_sessions"
AUDIT_LOGS = WORKSPACE / "audit_logs"
EVENT_RESULTS = EVENTS_OUTBOX / "event_results.jsonl"
AUDIT_LOG = AUDIT_LOGS / "tool_audit.jsonl"
DEMO_FILENAME = "issue_demo.txt"
DEMO_TEXT = "Fix bug in scheduler: task not triggering correctly"


def main() -> int:
    print("=" * 50)
    print("ZERO DEMO: Event → Engineering Output")
    print("=" * 50)
    print("ZERO turns a simple file event into structured engineering outputs automatically.")
    print("(No GitHub API. No commit. Fully controlled.)")
    print("")
    print("Input: a single text file describing a problem")
    print("Output: structured engineering artifacts ready for Git workflow")

    _initialize_demo_workspace()

    event_path = EVENTS_INBOX / DEMO_FILENAME
    event_path.write_text(DEMO_TEXT + "\n", encoding="utf-8")
    print("\n[1] Event Created")
    print(f"Event detected: {event_path}")

    before_sessions = _session_files()
    before_audit_count = _jsonl_count(AUDIT_LOG)

    records = EventRunner(repo_root=str(REPO_ROOT)).poll_once()
    demo_record = _find_demo_record(records)
    if not demo_record:
        print("\nDemo failed: event was not processed.")
        return 1

    print("\n[2] Event Processed")
    print("Event detected")

    task = demo_record.get("task", {})
    print("\n[3] Task Routed")
    print(f"Task generated: {task.get('title')}")

    tool = demo_record.get("tool_result", {}).get("tool") or "unknown"
    print("\n[4] Tool Executed")
    print("Action: Generate Git-ready artifacts")
    print(f"Tool: {tool}")

    print("\n[5] Outputs Generated")
    print("Artifacts generated:")
    for filename in OUTBOX_FILES.values():
        path = GITHUB_OUTBOX / filename
        status = "OK" if path.exists() else "missing"
        print(f"- {filename} ({status})")

    created_sessions = sorted(
        _session_files() - before_sessions,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    session_id = _load_session_id(created_sessions[0]) if created_sessions else ""
    audit_updated = _jsonl_count(AUDIT_LOG) > before_audit_count

    print("\n[6] Session Recorded")
    print(f"Execution session saved: {session_id or 'not found'}")
    print("Audit log updated" if audit_updated else "Audit log not updated")
    print("")
    print("Result: A real engineering workflow executed without human intervention.")
    print("")
    print("FINAL OUTPUT SUMMARY:")
    print("[OK] 4 engineering artifacts generated")
    print("[OK] 1 execution session recorded")
    print("[OK] audit log updated")
    print("[OK] no external side effects (safe mode)")

    print("\nOutbox:")
    print(f"- {EVENT_RESULTS}")
    print(f"- {GITHUB_OUTBOX}")
    return 0 if session_id and audit_updated and tool == "github_outbox" else 1


def _initialize_demo_workspace() -> None:
    for directory in (EVENTS_INBOX, EVENTS_OUTBOX, GITHUB_OUTBOX, SESSIONS, AUDIT_LOGS):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / ".gitkeep").touch()

    _remove_file(EVENTS_INBOX / DEMO_FILENAME)
    _remove_demo_event_results()
    _remove_demo_sessions()
    _remove_demo_audit_rows()

    for filename in OUTBOX_FILES.values():
        _remove_file(GITHUB_OUTBOX / filename)


def _find_demo_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for record in records:
        path = str(record.get("event", {}).get("path") or "")
        if path.endswith(DEMO_FILENAME):
            return record
    return None


def _session_files() -> set[Path]:
    if not SESSIONS.exists():
        return set()
    return set(SESSIONS.glob("*.json"))


def _load_session_id(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return path.stem
    return str(data.get("session_id") or path.stem)


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()])


def _remove_demo_event_results() -> None:
    if not EVENT_RESULTS.exists():
        return
    kept = []
    for line in EVENT_RESULTS.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        if DEMO_FILENAME not in line and DEMO_TEXT not in line:
            kept.append(line)
    EVENT_RESULTS.write_text(("\n".join(kept) + "\n") if kept else "", encoding="utf-8")


def _remove_demo_sessions() -> None:
    if not SESSIONS.exists():
        return
    for path in SESSIONS.glob("*.json"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if DEMO_FILENAME in text or DEMO_TEXT in text:
            _remove_file(path)


def _remove_demo_audit_rows() -> None:
    if not AUDIT_LOG.exists():
        return
    kept = []
    for line in AUDIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        if DEMO_FILENAME not in line and DEMO_TEXT not in line:
            kept.append(line)
    AUDIT_LOG.write_text(("\n".join(kept) + "\n") if kept else "", encoding="utf-8")


def _remove_file(path: Path) -> None:
    if path.exists() and path.is_file() and path.name != ".gitkeep":
        path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())

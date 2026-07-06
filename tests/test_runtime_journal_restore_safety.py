import json
from pathlib import Path

from core.runtime.runtime_journal import (
    JOURNAL_RESTORE_TRUNCATION_MARKER,
    RuntimeJournal,
)


def _deep_payload(depth: int) -> dict:
    payload = {
        "session_id": "session-deep",
        "status": "running",
        "event_type": "RuntimeStateTransitionEvent",
        "to_state": "RESTORING",
    }
    cursor = payload
    for index in range(depth):
        cursor["nested"] = {"level": index, "status": "kept"}
        cursor = cursor["nested"]
    return payload


def test_restore_from_old_deep_wal_projects_payload_without_hanging(tmp_path: Path) -> None:
    wal = tmp_path / "runtime.wal.jsonl"
    record = {
        "record_id": "old-wal-1",
        "runtime_version": "old",
        "abi_version": "old",
        "sequence": 1,
        "record_type": "runtime_event",
        "timestamp": "2026-07-06T00:00:00+00:00",
        "payload": _deep_payload(40),
        "metadata": {"phase": "restore", "items": [{"index": index} for index in range(100)]},
        "integrity_hash": "old-hash",
    }
    wal.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")

    restored = RuntimeJournal(wal).reconstruct()

    assert restored["record_count"] == 1
    restored_record = restored["records"][0]
    restored_payload = restored_record["payload"]
    assert restored_payload["session_id"] == "session-deep"
    assert restored_payload["status"] == "running"
    assert restored_payload["event_type"] == "RuntimeStateTransitionEvent"
    assert JOURNAL_RESTORE_TRUNCATION_MARKER in json.dumps(restored_record, sort_keys=True)
    assert len(restored_record["metadata"]["items"]) == 33


def test_restore_projection_handles_recursive_in_memory_payload() -> None:
    recursive = {"session_id": "session-recursive", "status": "running"}
    recursive["self"] = recursive

    journal = RuntimeJournal.from_records([])
    journal.append("runtime_memory_snapshot", payload=recursive)
    restored = journal.reconstruct()

    payload = restored["records"][0]["payload"]
    assert payload["session_id"] == "session-recursive"
    assert payload["self"] == JOURNAL_RESTORE_TRUNCATION_MARKER

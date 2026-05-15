from __future__ import annotations

from core.runtime.runtime_recovery_event_schema import (
    RUNTIME_RECOVERY_EVENT_SCHEMA,
    RUNTIME_RECOVERY_OPERATOR_SUMMARY_EVENT,
    build_runtime_recovery_event,
)


def test_build_runtime_recovery_event_from_operator_summary() -> None:
    event = build_runtime_recovery_event(
        event_id="event-1",
        task_id="task-1",
        recovery_id="recovery-1",
        operator_summary={
            "ok": True,
            "status": "ready",
            "readiness": "ready",
            "summary": "Recovery gate passed.",
            "blockers": [],
        },
    )

    assert event["ok"] is True
    assert event["schema"] == RUNTIME_RECOVERY_EVENT_SCHEMA
    assert event["event_type"] == RUNTIME_RECOVERY_OPERATOR_SUMMARY_EVENT
    assert event["event_id"] == "event-1"
    assert event["task_id"] == "task-1"
    assert event["recovery_id"] == "recovery-1"
    assert event["read_only"] is True
    assert event["executes_recovery"] is False
    assert event["executes_rollback"] is False
    assert event["executes_repair"] is False
    assert event["invokes_scheduler"] is False
    assert event["readiness"] == "ready"
    assert event["status"] == "ready"
    assert event["summary"] == "Recovery gate passed."
    assert event["blockers"] == []


def test_build_runtime_recovery_event_from_source_payload() -> None:
    event = build_runtime_recovery_event(
        source={
            "operator_summary": {
                "ok": False,
                "status": "blocked",
                "readiness": "blocked",
                "summary": "Blocked.",
                "blockers": ["blocked_contract"],
            }
        }
    )

    assert event["ok"] is False
    assert event["readiness"] == "blocked"
    assert event["status"] == "blocked"
    assert event["summary"] == "Blocked."
    assert event["blockers"] == ["blocked_contract"]


def test_build_runtime_recovery_event_is_json_safe() -> None:
    event = build_runtime_recovery_event(
        blockers=("a", "b"),
        operator_summary={"ok": False, "status": "blocked"},
    )

    assert event["blockers"] == ["a", "b"]
    assert event["status"] == "blocked"

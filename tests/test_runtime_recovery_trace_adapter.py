from __future__ import annotations

from core.runtime.runtime_recovery_observer import observe_runtime_recovery
from core.runtime.runtime_recovery_trace_adapter import (
    RuntimeRecoveryTraceAdapter,
    build_runtime_recovery_trace_event,
)


def test_trace_adapter_builds_event_from_operator_summary_payload() -> None:
    event = build_runtime_recovery_trace_event(
        {
            "operator_summary": {
                "ok": True,
                "status": "ready",
                "readiness": "ready",
                "summary": "Recovery gate passed.",
                "blockers": [],
            }
        },
        event_id="event-1",
        task_id="task-1",
        recovery_id="recovery-1",
    )

    assert event["ok"] is True
    assert event["schema"] == RuntimeRecoveryTraceAdapter.SCHEMA
    assert event["event_type"] == RuntimeRecoveryTraceAdapter.EVENT_TYPE
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


def test_trace_adapter_builds_event_from_observer_report() -> None:
    observer_report = observe_runtime_recovery(
        {
            "operator_summary": {
                "ok": False,
                "status": "blocked",
                "readiness": "blocked",
                "summary": "Recovery gate blocked runtime repair execution.",
                "blockers": ["missing confirmation"],
            }
        }
    )

    event = build_runtime_recovery_trace_event(observer_report)

    assert event["ok"] is False
    assert event["readiness"] == "blocked"
    assert event["status"] == "blocked"
    assert event["summary"] == "Recovery gate blocked runtime repair execution."
    assert event["blockers"] == ["missing confirmation"]


def test_trace_adapter_accepts_report_object_payload() -> None:
    class Report:
        payload = {
            "operator_summary": {
                "ok": False,
                "status": "blocked",
                "readiness": "blocked",
                "summary": "Blocked.",
                "blockers": ["blocked_contract"],
            }
        }

    event = build_runtime_recovery_trace_event(Report(), event_id="event-object")

    assert event["event_id"] == "event-object"
    assert event["ok"] is False
    assert event["blockers"] == ["blocked_contract"]

from __future__ import annotations

from core.runtime.runtime_recovery_trace_runtime_adapter import (
    RuntimeRecoveryTraceRuntimeAdapter,
    append_runtime_recovery_trace_event,
)
from core.tools.execution_trace import ExecutionTrace


def test_append_runtime_recovery_trace_event() -> None:
    trace = ExecutionTrace()

    result = append_runtime_recovery_trace_event(
        trace=trace,
        source={
            "operator_summary": {
                "ok": True,
                "status": "ready",
                "readiness": "ready",
                "summary": "Recovery gate passed.",
                "blockers": [],
            }
        },
    )

    assert result["event_type"] == RuntimeRecoveryTraceRuntimeAdapter.EVENT_TYPE
    assert len(trace.events) == 1

    payload = trace.events[0]["data"]

    assert payload["readiness"] == "ready"
    assert payload["status"] == "ready"
    assert payload["summary"] == "Recovery gate passed."
    assert payload["blockers"] == []


def test_append_runtime_recovery_trace_event_blocked() -> None:
    trace = ExecutionTrace()

    append_runtime_recovery_trace_event(
        trace=trace,
        source={
            "operator_summary": {
                "ok": False,
                "status": "blocked",
                "readiness": "blocked",
                "summary": "Blocked.",
                "blockers": ["missing confirmation"],
            }
        },
    )

    payload = trace.events[0]["data"]

    assert payload["readiness"] == "blocked"
    assert payload["blockers"] == ["missing confirmation"]

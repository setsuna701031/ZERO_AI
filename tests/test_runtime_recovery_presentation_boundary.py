from __future__ import annotations

from core.runtime.runtime_recovery_cli_presenter import render_runtime_recovery_cli
from core.runtime.runtime_recovery_event_schema import build_runtime_recovery_event
from core.runtime.runtime_recovery_observer import observe_runtime_recovery
from core.runtime.runtime_recovery_trace_adapter import build_runtime_recovery_trace_event


def test_runtime_recovery_presentation_boundary_end_to_end_ready() -> None:
    source = {
        "operator_summary": {
            "ok": True,
            "status": "ready",
            "readiness": "ready",
            "summary": "Recovery gate passed.",
            "blockers": [],
        }
    }

    observer = observe_runtime_recovery(source)
    event = build_runtime_recovery_event(source=observer)
    trace_event = build_runtime_recovery_trace_event(observer)
    cli_text = render_runtime_recovery_cli(trace_event)

    assert observer["readiness"] == "ready"
    assert event["readiness"] == "ready"
    assert trace_event["readiness"] == "ready"
    assert "Readiness: ready" in cli_text
    assert "Recovery gate passed." in cli_text


def test_runtime_recovery_presentation_boundary_end_to_end_blocked() -> None:
    source = {
        "operator_summary": {
            "ok": False,
            "status": "blocked",
            "readiness": "blocked",
            "summary": "Recovery gate blocked.",
            "blockers": ["missing confirmation"],
        }
    }

    observer = observe_runtime_recovery(source)
    event = build_runtime_recovery_event(source=observer)
    trace_event = build_runtime_recovery_trace_event(observer)
    cli_text = render_runtime_recovery_cli(trace_event)

    assert observer["readiness"] == "blocked"
    assert event["readiness"] == "blocked"
    assert trace_event["readiness"] == "blocked"
    assert "Readiness: blocked" in cli_text
    assert "- missing confirmation" in cli_text

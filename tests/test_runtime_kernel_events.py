from __future__ import annotations

from core.tasks.runtime_kernel_events import (
    normalize_runtime_kernel_event,
    normalize_runtime_kernel_events,
    summarize_normalized_kernel_events,
)


def test_normalize_runtime_kernel_events_returns_empty_for_none_or_empty_trace():
    assert normalize_runtime_kernel_events(None) == []
    assert normalize_runtime_kernel_events([]) == []


def test_normalize_runtime_kernel_event_preserves_raw_and_safe_fallbacks():
    event = normalize_runtime_kernel_event({"unexpected": "value"})

    assert event["source"] == "unknown"
    assert event["event_type"] == "unknown_event"
    assert event["status"] == "unknown"
    assert event["summary"] == "unknown_event"
    assert event["timestamp"] == ""
    assert event["raw"] == {"unexpected": "value"}


def test_normalize_runtime_kernel_events_accepts_malformed_event():
    events = normalize_runtime_kernel_events(["bad-event"])

    assert len(events) == 1
    assert events[0]["source"] == "unknown"
    assert events[0]["event_type"] == "unknown_event"
    assert events[0]["summary"] == "malformed event"
    assert events[0]["raw"] == "bad-event"


def test_blocker_event_extracts_reason():
    event = normalize_runtime_kernel_event(
        {
            "event": "task_blocked",
            "blocked_reason": "dependency unmet",
            "ts": 123,
        }
    )

    assert event["source"] == "blocker"
    assert event["event_type"] == "task_blocked"
    assert event["status"] == "blocked"
    assert event["summary"] == "blocker: dependency unmet"
    assert event["timestamp"] == 123


def test_execution_event_extracts_action_result_and_error():
    ok_event = normalize_runtime_kernel_event(
        {
            "event": "execution_gateway_completed",
            "type": "write_file",
            "result": {"ok": True, "action": "write_file"},
        }
    )
    failed_event = normalize_runtime_kernel_event(
        {
            "event": "execution_step_rejected",
            "action": "write_file",
            "result_error": "missing path",
        }
    )

    assert ok_event["source"] == "execution"
    assert ok_event["status"] == "ok"
    assert ok_event["summary"] == "execution action: write_file; result: write_file"
    assert failed_event["source"] == "execution"
    assert failed_event["status"] == "error"
    assert failed_event["summary"] == "execution action: write_file; error: missing path"


def test_planner_event_extracts_plan_step_and_intent():
    plan_event = normalize_runtime_kernel_event({"plan": {"goal": "create file"}, "ok": True})
    step_event = normalize_runtime_kernel_event({"step": {"description": "write content"}, "planner_gateway_ok": True})
    intent_event = normalize_runtime_kernel_event({"intent": "edit repo", "is_valid": True})

    assert plan_event["source"] == "planner"
    assert plan_event["summary"] == "planner: create file"
    assert step_event["source"] == "planner"
    assert step_event["summary"] == "planner: write content"
    assert intent_event["source"] == "planner"
    assert intent_event["summary"] == "planner: edit repo"


def test_explicit_sources_cover_repair_runtime_and_summary_counts():
    events = normalize_runtime_kernel_events(
        [
            {"event": "repair_patch_planned", "repair_action": "apply patch"},
            {"event_type": "runtime_step_started", "step": {"type": "run_command"}, "status": "running"},
        ]
    )
    summary = summarize_normalized_kernel_events(events)

    assert events[0]["source"] == "repair"
    assert events[0]["summary"] == "repair: apply patch"
    assert events[1]["source"] == "runtime"
    assert events[1]["summary"] == "runtime: run_command"
    assert summary["event_count"] == 2
    assert summary["by_source"]["repair"] == 1
    assert summary["by_source"]["runtime"] == 1
    assert summary["latest_event"]["event_type"] == "runtime_step_started"

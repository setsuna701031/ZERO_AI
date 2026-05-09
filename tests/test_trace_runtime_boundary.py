from __future__ import annotations

from pathlib import Path

from core.runtime.trace_runtime import TraceRuntime, build_trace_runtime


def test_trace_runtime_builds_stable_trace_file_path(tmp_path: Path) -> None:
    runtime = TraceRuntime(repo_root=tmp_path)

    path = runtime.trace_file_for_task(
        {
            "task_id": "task:demo/unsafe",
        }
    )

    assert path == tmp_path / "workspace" / "runtime_traces" / "task_demo_unsafe.json"


def test_trace_runtime_summarizes_dict_events() -> None:
    runtime = build_trace_runtime()

    summary = runtime.trace_summary(
        {
            "events": [
                {"status": "running"},
                {"status": "finished"},
            ]
        }
    )

    assert summary == {
        "event_count": 2,
        "has_events": True,
    }


def test_trace_runtime_reads_status_from_trace_or_last_event() -> None:
    runtime = build_trace_runtime()

    assert runtime.trace_status({"status": "finished"}) == "finished"
    assert runtime.trace_status({"events": [{"status": "running"}]}) == "running"
    assert runtime.trace_status({}) == "unknown"


def test_trace_runtime_builds_step_event() -> None:
    runtime = build_trace_runtime()

    event = runtime.trace_step(
        step_id="step_1",
        status="finished",
        message="ok",
        payload={"value": 1},
    )

    assert event["type"] == "step"
    assert event["step_id"] == "step_1"
    assert event["status"] == "finished"
    assert event["message"] == "ok"
    assert event["payload"] == {"value": 1}


def test_trace_runtime_builds_replan_event() -> None:
    runtime = build_trace_runtime()

    event = runtime.trace_replan(
        reason="verify failed",
        status="planned",
        payload={"attempt": 1},
    )

    assert event["type"] == "replan"
    assert event["reason"] == "verify failed"
    assert event["status"] == "planned"
    assert event["payload"] == {"attempt": 1}
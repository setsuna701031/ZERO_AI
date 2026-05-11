from __future__ import annotations

from core.display.runtime_presenter import (
    format_runtime_replay_detail,
    format_runtime_replay_summary,
)
from core.tasks.runtime_replay_narrative import build_runtime_replay_narrative
from core.tasks.runtime_replay_snapshot import build_runtime_replay_snapshot


def test_runtime_presenter_accepts_none_empty_and_malformed_input():
    for value in (None, {}, "bad-input"):
        summary = format_runtime_replay_summary(value)
        detail = format_runtime_replay_detail(value)

        assert "Runtime Replay Summary:" in summary
        assert "- task_id: <none>" in summary
        assert "- status: unknown" in summary
        assert "- summary: task is unknown with 0 replay event(s)." in summary
        assert "- next_observation: Inspect the replay snapshot fields before deciding the next human action." in summary
        assert "Runtime Replay Detail:" in detail
        assert "- timeline: No replay timeline events are available." in detail


def test_runtime_presenter_formats_snapshot_summary_with_failure_and_blocker():
    snapshot = build_runtime_replay_snapshot(
        {
            "task_id": "task-blocked",
            "status": "blocked",
            "goal": "write protected file",
            "blocked_reason": "review required",
            "blockers": [{"reason": "policy gate"}],
            "execution_trace": [
                {"event": "execution_step_rejected", "action": "write_file", "result_error": "blocked by policy"}
            ],
        }
    )

    text = format_runtime_replay_summary(snapshot)

    assert "Runtime Replay Summary:" in text
    assert "- task_id: task-blocked" in text
    assert "- status: blocked" in text
    assert "- summary: task-blocked is blocked" in text
    assert "- failure: 3 replay events need attention." in text
    assert "- blocker: 2 blockers are present. First blocker: policy gate." in text
    assert "- next_observation: Review the blocker before taking action: policy gate." in text


def test_runtime_presenter_formats_snapshot_detail_with_timeline():
    snapshot = build_runtime_replay_snapshot(
        {
            "task_id": "task-running",
            "status": "running",
            "goal": "write report",
            "runtime_trace": [{"event": "runtime_step_started", "status": "running"}],
        }
    )

    text = format_runtime_replay_detail(snapshot)

    assert "Runtime Replay Detail:" in text
    assert "- task_id: task-running" in text
    assert "- status: running" in text
    assert "- title: write report" in text
    assert "- summary: task-running is running with 1 replay event(s)." in text
    assert "- timeline: 0. runtime runtime_step_started: runtime: running" in text
    assert "- failure: No failed replay events were captured." in text
    assert "- blocker: No blockers were captured." in text
    assert "- next_observation: Check runtime: running and confirm the task is still progressing." in text


def test_runtime_presenter_accepts_prebuilt_narrative():
    snapshot = build_runtime_replay_snapshot(
        {
            "task_id": "task-finished",
            "status": "finished",
            "goal": "complete output",
            "execution_trace": [{"event": "execution_done", "ok": True, "is_valid": True}],
        }
    )
    narrative = build_runtime_replay_narrative(snapshot)

    summary = format_runtime_replay_summary(narrative)
    detail = format_runtime_replay_detail(narrative)

    assert "- task_id: task-finished" in summary
    assert "- status: finished" in summary
    assert "- title: complete output" in detail
    assert "Check the final output" in detail


def test_runtime_presenter_output_order_is_stable():
    text = format_runtime_replay_detail(
        {
            "task_id": "task-order",
            "status": "running",
            "title": "ordered",
            "summary": "ordered summary",
            "timeline_narrative": "ordered timeline",
            "failure_narrative": "ordered failure",
            "blocker_narrative": "ordered blocker",
            "next_observation": "ordered next",
        }
    )

    assert text.splitlines() == [
        "Runtime Replay Detail:",
        "- task_id: task-order",
        "- status: running",
        "- title: ordered",
        "- summary: ordered summary",
        "- timeline: ordered timeline",
        "- failure: ordered failure",
        "- blocker: ordered blocker",
        "- next_observation: ordered next",
    ]

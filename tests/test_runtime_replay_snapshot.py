from __future__ import annotations

from core.tasks.runtime_replay_snapshot import build_runtime_replay_snapshot


def test_runtime_replay_snapshot_accepts_none_empty_and_malformed_task():
    none_snapshot = build_runtime_replay_snapshot(None)
    empty_snapshot = build_runtime_replay_snapshot({})
    malformed_snapshot = build_runtime_replay_snapshot("bad-task")

    for snapshot in (none_snapshot, empty_snapshot, malformed_snapshot):
        assert snapshot["task_id"] == ""
        assert snapshot["status"] == "unknown"
        assert snapshot["goal"] == ""
        assert snapshot["kernel_status"]["kernel"]["status"] == "no_trace"
        assert snapshot["normalized_events"] == []
        assert snapshot["timeline"] == []
        assert snapshot["timeline_summary"]["event_count"] == 0
        assert snapshot["latest_event"] == {}
        assert snapshot["failed_events"] == []
        assert snapshot["blockers"] == []
        assert "unknown with 0 replay event(s)" in snapshot["replay_summary"]

    assert none_snapshot["raw_task"] is None
    assert malformed_snapshot["raw_task"] == "bad-task"


def test_runtime_replay_snapshot_packages_kernel_events_and_timeline():
    task = {
        "task_id": "task-1",
        "status": "running",
        "goal": "write report",
        "planner_trace": [
            {
                "event": "planner_contract_checked",
                "action": "write_file",
                "ok": True,
                "is_valid": True,
                "ts": 1,
            }
        ],
        "execution_trace": [
            {
                "event": "execution_gateway_completed",
                "type": "write_file",
                "ok": True,
                "is_valid": True,
                "result": {"ok": True, "action": "write_file"},
                "ts": 2,
            }
        ],
        "runtime_trace": [
            {
                "event": "runtime_step_started",
                "source": "runtime",
                "status": "running",
                "ts": 3,
            }
        ],
    }

    snapshot = build_runtime_replay_snapshot(task)

    assert snapshot["task_id"] == "task-1"
    assert snapshot["status"] == "running"
    assert snapshot["goal"] == "write report"
    assert snapshot["kernel_status"]["kernel"]["status"] == "healthy"
    assert snapshot["kernel_status"]["kernel"]["total_events"] == 2
    assert len(snapshot["normalized_events"]) == 3
    assert [item["sequence_index"] for item in snapshot["timeline"]] == [0, 1, 2]
    assert snapshot["timeline_summary"]["event_count"] == 3
    assert snapshot["latest_event"]["event_type"] == "runtime_step_started"
    assert snapshot["raw_task"] == task


def test_runtime_replay_snapshot_extracts_blockers_and_failed_events():
    task = {
        "task_id": "task-blocked",
        "status": "blocked",
        "goal": "dangerous write",
        "blocked_reason": "review required",
        "blockers": [{"reason": "policy gate"}],
        "execution_trace": [
            {
                "event": "execution_step_rejected",
                "action": "write_file",
                "result_error": "blocked by policy",
                "ts": 2,
            }
        ],
    }

    snapshot = build_runtime_replay_snapshot(task)

    assert snapshot["blockers"] == ["policy gate", "review required"]
    assert len(snapshot["failed_events"]) == 3
    assert snapshot["timeline_summary"]["failed_event_count"] == 3
    assert "Blocker: policy gate." in snapshot["replay_summary"]
    assert snapshot["kernel_status"]["kernel"]["status"] == "attention_required"


def test_runtime_replay_snapshot_stable_fallbacks_for_failed_finished_running():
    cases = [
        {
            "task_id": "task-failed",
            "status": "failed",
            "goal": "verify output",
            "execution_trace": [{"event": "execution_failed", "error": "boom", "ts": 1}],
        },
        {
            "task_id": "task-finished",
            "status": "finished",
            "goal": "complete output",
            "execution_trace": [{"event": "execution_done", "result": {"ok": True}, "ts": 1}],
        },
        {
            "task_id": "task-running",
            "status": "running",
            "goal": "continue work",
            "runtime_trace": [{"event": "runtime_step_started", "status": "running"}],
        },
    ]

    for task in cases:
        snapshot = build_runtime_replay_snapshot(task)

        assert snapshot["task_id"] == task["task_id"]
        assert snapshot["status"] == task["status"]
        assert snapshot["goal"] == task["goal"]
        assert isinstance(snapshot["replay_summary"], str)
        assert snapshot["replay_summary"]
        assert isinstance(snapshot["timeline"], list)
        assert isinstance(snapshot["normalized_events"], list)


def test_runtime_replay_snapshot_preserves_raw_event_and_timeline_traceability():
    raw_event = {"event": "repair_patch_planned", "repair_action": "apply patch", "ts": 4}
    task = {
        "task_id": "task-repair",
        "status": "running",
        "repair_trace": [raw_event],
    }

    snapshot = build_runtime_replay_snapshot(task)

    assert snapshot["normalized_events"][0]["raw"] == raw_event
    assert snapshot["timeline"][0]["raw"] == raw_event
    assert snapshot["latest_event"]["raw"] == raw_event

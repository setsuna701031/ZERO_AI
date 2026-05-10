from __future__ import annotations

from core.tasks.runtime_replay_narrative import build_runtime_replay_narrative
from core.tasks.runtime_replay_snapshot import build_runtime_replay_snapshot


def test_runtime_replay_narrative_accepts_none_empty_and_malformed_snapshot():
    for value in (None, {}, "bad-snapshot"):
        narrative = build_runtime_replay_narrative(value)

        assert narrative["task_id"] == ""
        assert narrative["status"] == "unknown"
        assert narrative["title"] == "task"
        assert "unknown with 0 replay event(s)" in narrative["summary"]
        assert narrative["timeline_narrative"] == "No replay timeline events are available."
        assert narrative["failure_narrative"] == "No failed replay events were captured."
        assert narrative["blocker_narrative"] == "No blockers were captured."
        assert narrative["next_observation"] == "Inspect the replay snapshot fields before deciding the next human action."
        assert narrative["raw_snapshot"] == value


def test_runtime_replay_narrative_builds_short_timeline_narrative():
    snapshot = {
        "task_id": "task-long",
        "status": "running",
        "goal": "write report",
        "timeline": [
            {"sequence_index": i, "source": "runtime", "event_type": f"event_{i}", "summary": f"step {i}"}
            for i in range(6)
        ],
        "failed_events": [],
        "blockers": [],
        "latest_event": {"summary": "step 5"},
    }

    narrative = build_runtime_replay_narrative(snapshot)

    assert narrative["task_id"] == "task-long"
    assert narrative["title"] == "write report"
    assert "0. runtime event_0: step 0" in narrative["timeline_narrative"]
    assert "3. runtime event_3: step 3" in narrative["timeline_narrative"]
    assert "event_4" not in narrative["timeline_narrative"]
    assert "... 2 more event(s) omitted." in narrative["timeline_narrative"]
    assert narrative["next_observation"] == "Check step 5 and confirm the task is still progressing."


def test_runtime_replay_narrative_uses_failed_events():
    snapshot = build_runtime_replay_snapshot(
        {
            "task_id": "task-failed",
            "status": "failed",
            "goal": "verify output",
            "execution_trace": [
                {"event": "execution_failed", "action": "verify", "error": "boom", "ts": 1}
            ],
        }
    )

    narrative = build_runtime_replay_narrative(snapshot)

    assert narrative["status"] == "failed"
    assert "event(s) need attention" in narrative["summary"]
    assert "One replay event needs attention:" in narrative["failure_narrative"]
    assert "execution action: verify; error: boom" in narrative["failure_narrative"]
    assert "Inspect execution action: verify; error: boom" in narrative["next_observation"]


def test_runtime_replay_narrative_uses_blockers_and_blocker_reason():
    snapshot = build_runtime_replay_snapshot(
        {
            "task_id": "task-blocked",
            "status": "blocked",
            "goal": "write protected file",
            "blocked_reason": "review required",
            "blockers": [{"reason": "policy gate"}],
        }
    )

    narrative = build_runtime_replay_narrative(snapshot)

    assert narrative["status"] == "blocked"
    assert "Primary blocker: policy gate." in narrative["summary"]
    assert narrative["blocker_narrative"] == "2 blockers are present. First blocker: policy gate."
    assert narrative["next_observation"] == "Review the blocker before taking action: policy gate."


def test_runtime_replay_narrative_stable_for_finished_and_running_tasks():
    finished = build_runtime_replay_snapshot(
        {
            "task_id": "task-finished",
            "status": "finished",
            "goal": "complete output",
            "execution_trace": [{"event": "execution_done", "ok": True, "is_valid": True, "ts": 1}],
        }
    )
    running = build_runtime_replay_snapshot(
        {
            "task_id": "task-running",
            "status": "running",
            "goal": "continue output",
            "runtime_trace": [{"event": "runtime_step_started", "status": "running"}],
        }
    )

    finished_narrative = build_runtime_replay_narrative(finished)
    running_narrative = build_runtime_replay_narrative(running)

    assert finished_narrative["failure_narrative"] == "No failed replay events were captured."
    assert finished_narrative["blocker_narrative"] == "No blockers were captured."
    assert finished_narrative["next_observation"] == "Check the final output and confirm the replay timeline matches the expected task flow."
    assert running_narrative["next_observation"] == "Check runtime: running and confirm the task is still progressing."


def test_runtime_replay_narrative_preserves_raw_snapshot():
    snapshot = {"task_id": "task-raw", "status": "running", "custom": {"keep": True}}

    narrative = build_runtime_replay_narrative(snapshot)

    assert narrative["raw_snapshot"] == snapshot
    snapshot["custom"]["keep"] = False
    assert narrative["raw_snapshot"]["custom"]["keep"] is True

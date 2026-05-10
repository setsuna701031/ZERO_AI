from __future__ import annotations

import json
from pathlib import Path

from core.tasks.runtime_audit_artifact import (
    RUNTIME_AUDIT_ARTIFACT_TYPE,
    RUNTIME_AUDIT_ARTIFACT_VERSION,
    build_runtime_audit_artifact,
)
from core.tasks.runtime_replay_narrative import build_runtime_replay_narrative
from core.tasks.runtime_replay_snapshot import build_runtime_replay_snapshot


def test_runtime_audit_artifact_accepts_none_empty_and_malformed_input():
    for value in (None, {}, "bad-snapshot"):
        artifact = build_runtime_audit_artifact(value)

        assert artifact["artifact_type"] == RUNTIME_AUDIT_ARTIFACT_TYPE
        assert artifact["artifact_version"] == RUNTIME_AUDIT_ARTIFACT_VERSION
        assert artifact["artifact_id"].startswith("runtime_audit:")
        assert artifact["task_id"] == ""
        assert artifact["status"] == "unknown"
        assert artifact["goal"] == ""
        assert "unknown with 0 replay event(s)" in artifact["narrative_summary"]
        assert artifact["timeline_summary"] == {}
        assert artifact["kernel_status"] == {}
        assert artifact["normalized_events"] == []
        assert artifact["timeline"] == []
        assert artifact["blockers"] == []
        assert artifact["failed_events"] == []
        json.dumps(artifact)


def test_runtime_audit_artifact_wraps_snapshot_and_generated_narrative():
    snapshot = build_runtime_replay_snapshot(
        {
            "task_id": "task-1",
            "status": "running",
            "goal": "write report",
            "planner_trace": [{"event": "planner_contract_checked", "ok": True, "is_valid": True, "ts": 1}],
            "execution_trace": [{"event": "execution_done", "ok": True, "is_valid": True, "ts": 2}],
            "runtime_trace": [{"event": "runtime_step_started", "status": "running", "ts": 3}],
        }
    )

    artifact = build_runtime_audit_artifact(snapshot)

    assert artifact["task_id"] == "task-1"
    assert artifact["artifact_id"].startswith("runtime_audit:task-1:running:")
    assert artifact["status"] == "running"
    assert artifact["goal"] == "write report"
    assert artifact["summary"] == snapshot["replay_summary"]
    assert artifact["timeline_summary"]["event_count"] == 3
    assert artifact["kernel_status"]["kernel"]["status"] == "healthy"
    assert len(artifact["normalized_events"]) == 3
    assert len(artifact["timeline"]) == 3
    assert artifact["raw_snapshot"] == snapshot
    assert artifact["raw_narrative"]["task_id"] == "task-1"
    json.dumps(artifact)


def test_runtime_audit_artifact_accepts_explicit_narrative():
    snapshot = build_runtime_replay_snapshot(
        {
            "task_id": "task-finished",
            "status": "finished",
            "goal": "complete output",
            "execution_trace": [{"event": "execution_done", "ok": True, "is_valid": True}],
        }
    )
    narrative = build_runtime_replay_narrative(snapshot)
    narrative["summary"] = "custom narrative summary"

    artifact = build_runtime_audit_artifact(snapshot, narrative=narrative)

    assert artifact["narrative_summary"] == "custom narrative summary"
    assert artifact["raw_narrative"] == narrative
    assert artifact["next_observation"] == narrative["next_observation"]


def test_runtime_audit_artifact_is_json_safe_for_non_serializable_raw_values():
    snapshot = build_runtime_replay_snapshot(
        {
            "task_id": "task-json",
            "status": "running",
            "goal": "serialize",
            "custom_path": Path("workspace/output.txt"),
        }
    )
    snapshot["raw_task"]["custom_path"] = Path("workspace/output.txt")
    narrative = build_runtime_replay_narrative(snapshot)
    narrative["raw_snapshot"]["raw_task"]["custom_path"] = Path("workspace/output.txt")

    artifact = build_runtime_audit_artifact(snapshot, narrative=narrative)

    assert artifact["raw_snapshot"]["raw_task"]["custom_path"] == "workspace\\output.txt" or artifact["raw_snapshot"]["raw_task"]["custom_path"] == "workspace/output.txt"
    json.dumps(artifact)


def test_runtime_audit_artifact_stable_for_blocked_failed_finished_running():
    cases = [
        {
            "task_id": "task-blocked",
            "status": "blocked",
            "goal": "protected write",
            "blocked_reason": "review required",
        },
        {
            "task_id": "task-failed",
            "status": "failed",
            "goal": "verify output",
            "execution_trace": [{"event": "execution_failed", "error": "boom"}],
        },
        {
            "task_id": "task-finished",
            "status": "finished",
            "goal": "done",
            "execution_trace": [{"event": "execution_done", "ok": True, "is_valid": True}],
        },
        {
            "task_id": "task-running",
            "status": "running",
            "goal": "continue",
            "runtime_trace": [{"event": "runtime_step_started", "status": "running"}],
        },
    ]

    for task in cases:
        snapshot = build_runtime_replay_snapshot(task)
        artifact = build_runtime_audit_artifact(snapshot)

        assert artifact["task_id"] == task["task_id"]
        assert artifact["status"] == task["status"]
        assert artifact["goal"] == task["goal"]
        assert isinstance(artifact["narrative_summary"], str)
        assert isinstance(artifact["failure_summary"], str)
        assert isinstance(artifact["blocker_summary"], str)
        assert isinstance(artifact["next_observation"], str)
        json.dumps(artifact)

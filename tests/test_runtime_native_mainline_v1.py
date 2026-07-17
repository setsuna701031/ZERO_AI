from __future__ import annotations

from core.runtime.runtime_native_mainline import (
    MAINLINE_STATUS_BLOCKED,
    MAINLINE_STATUS_COMPLETED,
    RuntimeNativeMainline,
    RuntimeNativeMainlineConfig,
)


def test_runtime_native_mainline_config_preserves_empty_capabilities():
    config = RuntimeNativeMainlineConfig.from_dict({"capabilities": []})
    assert config.capabilities == []


def test_runtime_native_mainline_boot_health(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path,
        config={
            "runtime_id": "mainline-runtime",
            "owner_id": "mainline-owner",
            "source_session_id": "mainline-session",
        },
    )

    health = mainline.health()

    assert health["ok"] is True
    assert health["lease_sessions"] == 1
    assert health["watchdog_sessions"] == 1
    assert health["mainline_status"] == "ready"


def test_runtime_native_mainline_runs_simple_goal(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path,
        config={
            "runtime_id": "mainline-simple-runtime",
            "owner_id": "simple-owner",
            "source_session_id": "simple-session",
        },
    )

    result = mainline.run_goal(
        "simple mainline goal",
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "a"},
                {"type": "work", "name": "b"},
            ],
        },
        step_runner=lambda step, context: {"ok": True, "name": step["name"]},
    )

    assert result.status == MAINLINE_STATUS_COMPLETED
    assert result.execution_id
    assert result.loop_record["status"] == "completed"
    assert len(result.loop_record["cycles"]) == 2


def test_runtime_native_mainline_recovers_and_resumes_goal(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path,
        config={
            "runtime_id": "mainline-recovery-runtime",
            "owner_id": "recovery-owner",
            "source_session_id": "recovery-session",
        },
    )

    failed_once = {"value": False}

    def runner(step, context):
        if step["name"] == "repairable" and not failed_once["value"]:
            failed_once["value"] = True
            return {"ok": False, "failed": True, "message": "planned failure"}
        return {"ok": True, "name": step["name"]}

    result = mainline.run_goal(
        "recover mainline goal",
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
        step_runner=runner,
        resume_runner=lambda step, context: {"ok": True, "name": step["name"]},
        current_tick=2,
    )

    assert result.status == MAINLINE_STATUS_COMPLETED
    assert result.loop_record["task"]["continuation_ref"]["resume_step_index"] == 2
    assert len(result.recovery_tickets) == 1
    assert result.recovery_tickets[0]["status"] == "completed"


def test_runtime_native_mainline_blocks_when_authority_denied(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path,
        config={
            "runtime_id": "mainline-blocked-runtime",
            "owner_id": "blocked-owner",
            "source_session_id": "blocked-session",
            "capabilities": [],
        },
    )

    result = mainline.run_goal(
        "blocked goal",
        planner_fn=lambda goal, context: {"steps": [{"type": "work"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    assert result.status == MAINLINE_STATUS_BLOCKED
    assert result.authority_decision["decision"] == "deny"


def test_runtime_native_mainline_legacy_request_adapter(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path,
        config={
            "runtime_id": "legacy-mainline-runtime",
            "owner_id": "legacy-owner",
            "source_session_id": "legacy-session",
        },
    )

    result = mainline.run_legacy_request(
        {
            "task_id": "legacy-task",
            "prompt": "legacy prompt task",
        },
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "legacy"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    assert result.status == MAINLINE_STATUS_COMPLETED
    assert result.task_id == "legacy-task"


def test_runtime_native_mainline_persists_results(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path,
        config={
            "runtime_id": "persist-mainline-runtime",
            "owner_id": "persist-owner",
            "source_session_id": "persist-session",
        },
    )

    first = mainline.run_goal(
        "persisted goal",
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "persist"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    reloaded = RuntimeNativeMainline.with_workspace(tmp_path)
    latest = reloaded.latest_result()

    assert latest is not None
    assert latest.run_id == first.run_id
    assert latest.status == MAINLINE_STATUS_COMPLETED

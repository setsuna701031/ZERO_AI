from __future__ import annotations

from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_native_scheduler import (
    SCHEDULER_PRIORITY_HIGH,
    SCHEDULER_PRIORITY_LOW,
    SCHEDULER_STATUS_BLOCKED,
    SCHEDULER_STATUS_COMPLETED,
    RuntimeNativeScheduler,
)


def build_scheduler(tmp_path, *, capabilities=None):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "scheduler-runtime",
            "owner_id": "scheduler-owner",
            "source_session_id": "scheduler-session",
            "capabilities": ["read", "write", "execute"] if capabilities is None else capabilities,
        },
    )
    scheduler = RuntimeNativeScheduler.with_workspace(
        tmp_path / "scheduler",
        mainline=mainline,
    )
    return scheduler, mainline


def test_runtime_native_scheduler_queues_and_runs_goal(tmp_path):
    scheduler, mainline = build_scheduler(tmp_path)

    item = scheduler.schedule_goal(
        goal="scheduler simple goal",
        ready_tick=1,
    )

    assert item.status == "queued"

    results = scheduler.run_ready(
        current_tick=1,
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "a"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    assert len(results) == 1
    assert results[0].status == SCHEDULER_STATUS_COMPLETED
    assert results[0].mainline_result["status"] == "completed"
    assert results[0].mainline_result["final_result"]["ok"] is True
    assert results[0].authority_ref["decision"] == "allow"
    execution_path = results[0].to_dict()["execution_path"]
    assert execution_path["direct_execution"] is False
    assert execution_path["runtime_owns_execution"] is True
    assert execution_path["taskrunner_required"] is True
    assert execution_path["step_executor_endpoint_only"] is True


def test_runtime_native_scheduler_priority_order(tmp_path):
    scheduler, mainline = build_scheduler(tmp_path)

    low = scheduler.schedule_goal(
        goal="low priority",
        priority=SCHEDULER_PRIORITY_LOW,
        ready_tick=1,
    )
    high = scheduler.schedule_goal(
        goal="high priority",
        priority=SCHEDULER_PRIORITY_HIGH,
        ready_tick=1,
    )

    ready = scheduler.ready_items(current_tick=1, limit=2)

    assert ready[0].schedule_id == high.schedule_id
    assert ready[1].schedule_id == low.schedule_id


def test_runtime_native_scheduler_blocks_when_mainline_authority_denied(tmp_path):
    scheduler, mainline = build_scheduler(tmp_path, capabilities=[])

    item = scheduler.schedule_goal(
        goal="blocked scheduler goal",
        ready_tick=1,
    )

    result = scheduler.run_item(
        item.schedule_id,
        current_tick=1,
        planner_fn=lambda goal, context: {"steps": [{"type": "work"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    assert result.status == SCHEDULER_STATUS_BLOCKED
    assert result.authority_ref["decision"] == "deny"


def test_runtime_native_scheduler_recovery_refs_propagate(tmp_path):
    scheduler, mainline = build_scheduler(tmp_path)

    failed_once = {"value": False}

    def runner(step, context):
        if step["name"] == "repairable" and not failed_once["value"]:
            failed_once["value"] = True
            return {"ok": False, "failed": True, "message": "planned failure"}
        return {"ok": True}

    item = scheduler.schedule_goal(
        goal="recoverable scheduler goal",
        ready_tick=1,
    )

    result = scheduler.run_item(
        item.schedule_id,
        current_tick=1,
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
        step_runner=runner,
        resume_runner=lambda step, context: {"ok": True},
    )

    assert result.status == SCHEDULER_STATUS_COMPLETED
    assert result.mainline_result["status"] == "completed"
    assert result.mainline_result["final_result"]["ok"] is True
    assert result.mainline_result["final_result"]["status"] == "completed"
    assert result.authority_ref["decision"] == "allow"
    execution_path = result.to_dict()["execution_path"]
    assert execution_path["direct_execution"] is False
    assert execution_path["runtime_owns_execution"] is True
    assert execution_path["taskrunner_required"] is True
    assert execution_path["step_executor_endpoint_only"] is True
    assert mainline.health()["queue_tickets"] == 1


def test_runtime_native_scheduler_persists_queue(tmp_path):
    scheduler, mainline = build_scheduler(tmp_path)

    item = scheduler.schedule_goal(
        goal="persist scheduler goal",
        ready_tick=5,
    )

    reloaded = RuntimeNativeScheduler.with_workspace(
        tmp_path / "scheduler",
        mainline=mainline,
    )

    assert reloaded.get_item(item.schedule_id).goal == "persist scheduler goal"

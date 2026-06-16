from __future__ import annotations

from core.runtime.runtime_native_execution_dispatch import (
    DISPATCH_NODE_CONTINUATION,
    DISPATCH_NODE_ENTRY,
    DISPATCH_NODE_EXECUTION,
    DISPATCH_STATUS_BLOCKED,
    DISPATCH_STATUS_COMPLETED,
    DISPATCH_STATUS_FAILED,
    RuntimeNativeExecutionDispatch,
)
from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_native_scheduler import RuntimeNativeScheduler


def build_dispatch(tmp_path, *, capabilities=None):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "dispatch-runtime",
            "owner_id": "dispatch-owner",
            "source_session_id": "dispatch-session",
            "capabilities": ["read", "write", "execute"] if capabilities is None else capabilities,
        },
    )
    scheduler = RuntimeNativeScheduler.with_workspace(
        tmp_path / "scheduler",
        mainline=mainline,
    )
    dispatch = RuntimeNativeExecutionDispatch.with_workspace(
        tmp_path / "dispatch",
        mainline=mainline,
        scheduler=scheduler,
    )
    return dispatch, scheduler, mainline


def test_runtime_native_dispatch_runs_goal(tmp_path):
    dispatch, scheduler, mainline = build_dispatch(tmp_path)

    result = dispatch.dispatch_goal(
        goal="dispatch simple goal",
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "a"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    assert result.status == DISPATCH_STATUS_FAILED
    assert result.mainline_result["final_result"]["error"] == (
        "legacy_runtime_dispatcher_migration_required"
    )
    assert result.execution_id
    assert result.nodes[0].node_type == DISPATCH_NODE_ENTRY
    assert any(node.node_type == DISPATCH_NODE_EXECUTION for node in result.nodes)
    assert dispatch.execution_map()[result.execution_id]["dispatch_id"] == result.dispatch_id


def test_runtime_native_dispatch_recovery_continuation_graph(tmp_path):
    dispatch, scheduler, mainline = build_dispatch(tmp_path)
    failed_once = {"value": False}

    def runner(step, context):
        if step["name"] == "repairable" and not failed_once["value"]:
            failed_once["value"] = True
            return {"ok": False, "failed": True, "message": "planned dispatch failure"}
        return {"ok": True}

    result = dispatch.dispatch_goal(
        goal="dispatch recoverable goal",
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
        step_runner=runner,
        resume_runner=lambda step, context: {"ok": True},
        current_tick=2,
    )

    assert result.status == DISPATCH_STATUS_FAILED
    assert result.mainline_result["final_result"]["error"] == (
        "legacy_runtime_dispatcher_migration_required"
    )


def test_runtime_native_dispatch_blocks_authority_denied(tmp_path):
    dispatch, scheduler, mainline = build_dispatch(tmp_path, capabilities=[])

    result = dispatch.dispatch_goal(
        goal="dispatch blocked goal",
        planner_fn=lambda goal, context: {"steps": [{"type": "work"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    assert result.status == DISPATCH_STATUS_BLOCKED
    assert result.authority_ref["decision"] == "deny"


def test_runtime_native_dispatch_from_schedule_item(tmp_path):
    dispatch, scheduler, mainline = build_dispatch(tmp_path)

    item = scheduler.schedule_goal(
        goal="dispatch from schedule",
        task_id="scheduled-dispatch-task",
        ready_tick=1,
    )

    result = dispatch.dispatch_schedule_item(
        item,
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "scheduled"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    assert result.status == DISPATCH_STATUS_FAILED
    assert result.mainline_result["final_result"]["error"] == (
        "legacy_runtime_dispatcher_migration_required"
    )
    assert result.schedule_id == item.schedule_id
    assert result.task_id == "scheduled-dispatch-task"


def test_runtime_native_dispatch_persists(tmp_path):
    dispatch, scheduler, mainline = build_dispatch(tmp_path)

    result = dispatch.dispatch_goal(
        goal="persist dispatch",
        planner_fn=lambda goal, context: {"steps": [{"type": "work"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    reloaded = RuntimeNativeExecutionDispatch.with_workspace(
        tmp_path / "dispatch",
        mainline=mainline,
        scheduler=scheduler,
    )

    assert reloaded.get_dispatch(result.dispatch_id).dispatch_id == result.dispatch_id

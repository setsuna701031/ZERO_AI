from __future__ import annotations

from core.runtime.runtime_native_execution_dispatch import RuntimeNativeExecutionDispatch
from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_native_scheduler import RuntimeNativeScheduler


def test_runtime_native_execution_dispatch_migration_seal(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "dispatch-seal-runtime",
            "namespace": "zero.dispatch.seal",
            "owner_id": "dispatch-seal-owner",
            "source_session_id": "dispatch-seal-session",
            "allowed_paths": ["aer://task/", "workspace/"],
            "denied_paths": ["workspace/system/"],
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

    failed_once = {"value": False}

    def runner(step, context):
        if step["name"] == "repairable" and not failed_once["value"]:
            failed_once["value"] = True
            return {"ok": False, "failed": True, "message": "planned dispatch seal failure"}
        return {"ok": True, "name": step["name"]}

    item = scheduler.schedule_goal(
        goal="runtime-native execution dispatch migration seal",
        task_id="dispatch-seal-task",
        ready_tick=1,
        priority=90,
    )

    result = dispatch.dispatch_schedule_item(
        item,
        current_tick=2,
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
        step_runner=runner,
        resume_runner=lambda step, context: {"ok": True, "name": step["name"]},
    )

    assert result.status == "failed"
    assert result.task_id == "dispatch-seal-task"
    assert result.schedule_id == item.schedule_id
    assert result.execution_id
    assert result.mainline_result["final_result"]["error"] == (
        "legacy_runtime_dispatcher_migration_required"
    )
    assert dispatch.execution_map()[result.execution_id]["dispatch_id"] == result.dispatch_id

    health = dispatch.health()
    assert health["counts"]["failed"] == 1
    assert health["execution_map_size"] == 1

    mainline_health = mainline.health()
    assert mainline_health["queue_tickets"] == 1
    assert mainline_health["execution_records"] == 1

    lineage = mainline.orchestrator.lineage.lineage_for_ref("dispatch-seal-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}
    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "runtime_replay" in node_types

    tick = mainline.supervisor_bridge.tick(current_tick=3).to_dict()
    assert tick["watchdog_lease_result"]["incident_count"] == 0


def test_runtime_native_execution_dispatch_seal_reload(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "dispatch-reload-runtime",
            "owner_id": "dispatch-reload-owner",
            "source_session_id": "dispatch-reload-session",
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

    result = dispatch.dispatch_goal(
        goal="reload dispatch goal",
        planner_fn=lambda goal, context: {"steps": [{"type": "work"}]},
        step_runner=lambda step, context: {"ok": True},
    )

    reloaded_mainline = RuntimeNativeMainline.with_workspace(tmp_path / "mainline")
    reloaded_scheduler = RuntimeNativeScheduler.with_workspace(
        tmp_path / "scheduler",
        mainline=reloaded_mainline,
    )
    reloaded_dispatch = RuntimeNativeExecutionDispatch.with_workspace(
        tmp_path / "dispatch",
        mainline=reloaded_mainline,
        scheduler=reloaded_scheduler,
    )

    loaded = reloaded_dispatch.get_dispatch(result.dispatch_id)
    assert loaded.dispatch_id == result.dispatch_id
    assert loaded.status == "failed"

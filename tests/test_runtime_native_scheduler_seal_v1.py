from __future__ import annotations

from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_native_scheduler import RuntimeNativeScheduler
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def test_runtime_native_scheduler_dispatch_authority_seal(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "scheduler-seal-runtime",
            "namespace": "zero.scheduler.seal",
            "owner_id": "scheduler-seal-owner",
            "source_session_id": "scheduler-seal-session",
            "allowed_paths": ["aer://task/", "workspace/"],
            "denied_paths": ["workspace/system/"],
        },
    )
    scheduler = RuntimeNativeScheduler.with_workspace(
        tmp_path / "scheduler",
        mainline=mainline,
    )

    failed_once = {"value": False}

    def runner(step, context):
        if step["name"] == "repairable" and not failed_once["value"]:
            failed_once["value"] = True
            return {"ok": False, "failed": True, "message": "planned scheduler seal failure"}
        return {"ok": True, "name": step["name"]}

    item = scheduler.schedule_goal(
        goal="runtime-native scheduler migration seal",
        task_id="scheduler-seal-task",
        ready_tick=1,
        priority=90,
        metadata={"seal": True},
    )

    result = scheduler.run_item(
        item.schedule_id,
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

    assert result.status == "completed"
    assert result.task_id == "scheduler-seal-task"
    assert result.mainline_result["status"] == "completed"
    assert result.mainline_result["final_result"]["ok"] is True
    assert result.mainline_result["final_result"]["status"] == "completed"
    assert result.authority_ref["decision"] == "allow"
    execution_path = result.to_dict()["execution_path"]
    assert execution_path["direct_execution"] is False
    assert execution_path["runtime_owns_execution"] is True
    assert execution_path["taskrunner_required"] is True
    assert execution_path["step_executor_endpoint_only"] is True

    health = scheduler.health()
    assert health["counts"]["completed"] == 1

    mainline_health = mainline.health()
    assert mainline_health["queue_tickets"] == 1
    assert mainline_health["execution_records"] == 1

    lineage = mainline.orchestrator.lineage.lineage_for_ref("scheduler-seal-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}
    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "recovery" in node_types
    assert "runtime_replay" in node_types

    tick = mainline.supervisor_bridge.tick(current_tick=3).to_dict()
    assert tick["watchdog_lease_result"]["incident_count"] == 0


def test_runtime_native_scheduler_seal_persistence_reload(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "scheduler-reload-runtime",
            "owner_id": "scheduler-reload-owner",
            "source_session_id": "scheduler-reload-session",
        },
    )
    scheduler = RuntimeNativeScheduler.with_workspace(
        tmp_path / "scheduler",
        mainline=mainline,
    )

    item = scheduler.schedule_goal(
        goal="reload scheduler goal",
        ready_tick=10,
    )

    reloaded_mainline = RuntimeNativeMainline.with_workspace(tmp_path / "mainline")
    reloaded_scheduler = RuntimeNativeScheduler.with_workspace(
        tmp_path / "scheduler",
        mainline=reloaded_mainline,
    )

    assert reloaded_scheduler.get_item(item.schedule_id).goal == "reload scheduler goal"

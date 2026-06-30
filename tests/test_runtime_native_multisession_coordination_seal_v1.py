from __future__ import annotations

from core.runtime.runtime_native_execution_dispatch import RuntimeNativeExecutionDispatch
from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_native_multisession_coordination import RuntimeNativeMultiSessionCoordination
from core.runtime.runtime_native_scheduler import RuntimeNativeScheduler
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def test_runtime_native_multisession_coordination_seal(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "mesh-main-runtime",
            "namespace": "zero.mesh.main",
            "owner_id": "mesh-owner",
            "source_session_id": "mesh-session",
            "allowed_paths": ["aer://task/", "workspace/", "runtime-signal://"],
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
    coord = RuntimeNativeMultiSessionCoordination.with_workspace(
        tmp_path / "coordination",
        mainline=mainline,
        scheduler=scheduler,
        dispatch=dispatch,
    )

    planner_node = coord.register_node(
        runtime_id="planner-runtime",
        namespace="zero.mesh.planner",
        owner_id="planner-owner",
        source_session_id="planner-session",
        role="planner",
    )
    execution_node = coord.register_node(
        runtime_id="mesh-main-runtime",
        namespace="zero.mesh.execution",
        owner_id="mesh-owner",
        source_session_id="mesh-session",
        role="execution",
    )
    recovery_node = coord.register_node(
        runtime_id="mesh-main-runtime",
        namespace="zero.mesh.recovery",
        owner_id="mesh-owner",
        source_session_id="mesh-session",
        role="recovery",
    )

    rv = coord.open_rendezvous(
        name="mesh startup",
        required_node_ids=[planner_node.node_id, execution_node.node_id, recovery_node.node_id],
    )
    coord.join_rendezvous(rv.rendezvous_id, planner_node.node_id)
    coord.join_rendezvous(rv.rendezvous_id, execution_node.node_id)
    completed_rv = coord.join_rendezvous(rv.rendezvous_id, recovery_node.node_id)
    assert completed_rv.status == "completed"

    failed_once = {"value": False}

    def runner(step, context):
        if step["name"] == "repairable" and not failed_once["value"]:
            failed_once["value"] = True
            return {"ok": False, "failed": True, "message": "planned mesh failure"}
        return {"ok": True, "name": step["name"]}

    result = coord.dispatch_between_nodes(
        source_node_id=planner_node.node_id,
        target_node_id=execution_node.node_id,
        goal="multi-session coordinated execution",
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

    assert result["ok"] is True
    assert result["dispatch"]["status"] == "completed"
    assert result["dispatch"]["continuation_ref"]["resume_step_index"] == 2
    assert result["dispatch"]["recovery_ref"]["recovery_ticket"]["status"] == "completed"

    recovery_signal = coord.send_signal(
        source_node_id=execution_node.node_id,
        target_node_id=recovery_node.node_id,
        signal_type="recovery_request",
        payload={"task_id": "mesh-recovery-task", "current_tick": 3},
    )
    delivered_recovery = coord.deliver_signal(recovery_signal.signal_id)
    assert delivered_recovery.status == "delivered"
    assert delivered_recovery.recovery_ref["recovery_ticket"]["source_session_id"] == "mesh-session"

    health = coord.health()
    assert health["nodes"] == 3
    assert health["signals"] == 2
    assert health["rendezvous"] == 1

    lineage = mainline.orchestrator.lineage.lineage_for_ref("mesh-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}
    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "runtime_replay" in node_types

    tick = mainline.supervisor_bridge.tick(current_tick=4).to_dict()
    assert tick["watchdog_lease_result"]["incident_count"] == 0


def test_runtime_native_multisession_coordination_seal_reload(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "mesh-reload-runtime",
            "owner_id": "mesh-reload-owner",
            "source_session_id": "mesh-reload-session",
            "allowed_paths": ["aer://task/", "workspace/", "runtime-signal://"],
        },
    )
    scheduler = RuntimeNativeScheduler.with_workspace(tmp_path / "scheduler", mainline=mainline)
    dispatch = RuntimeNativeExecutionDispatch.with_workspace(tmp_path / "dispatch", mainline=mainline, scheduler=scheduler)
    coord = RuntimeNativeMultiSessionCoordination.with_workspace(tmp_path / "coordination", mainline=mainline, scheduler=scheduler, dispatch=dispatch)

    node = coord.register_node(runtime_id="mesh-reload-runtime", namespace="zero.mesh.reload", owner_id="mesh-reload-owner")

    reloaded_mainline = RuntimeNativeMainline.with_workspace(tmp_path / "mainline")
    reloaded_scheduler = RuntimeNativeScheduler.with_workspace(tmp_path / "scheduler", mainline=reloaded_mainline)
    reloaded_dispatch = RuntimeNativeExecutionDispatch.with_workspace(tmp_path / "dispatch", mainline=reloaded_mainline, scheduler=reloaded_scheduler)
    reloaded_coord = RuntimeNativeMultiSessionCoordination.with_workspace(
        tmp_path / "coordination",
        mainline=reloaded_mainline,
        scheduler=reloaded_scheduler,
        dispatch=reloaded_dispatch,
    )

    assert reloaded_coord.get_node(node.node_id).runtime_id == "mesh-reload-runtime"

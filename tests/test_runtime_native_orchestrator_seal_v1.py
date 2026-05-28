from __future__ import annotations

from core.runtime.runtime_native_execution_dispatch import RuntimeNativeExecutionDispatch
from core.runtime.runtime_native_mainline import RuntimeNativeMainline
from core.runtime.runtime_native_multisession_coordination import RuntimeNativeMultiSessionCoordination
from core.runtime.runtime_native_scheduler import RuntimeNativeScheduler


def build_orchestrator_stack(tmp_path):
    mainline = RuntimeNativeMainline.with_workspace(
        tmp_path / "mainline",
        config={
            "runtime_id": "orchestrator-seal-runtime",
            "namespace": "zero.orchestrator.seal",
            "owner_id": "orchestrator-owner",
            "source_session_id": "orchestrator-session",
            "allowed_paths": [
                "aer://task/",
                "workspace/",
                "runtime-signal://",
            ],
            "denied_paths": [
                "workspace/system/",
            ],
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

    coordination = RuntimeNativeMultiSessionCoordination.with_workspace(
        tmp_path / "coordination",
        mainline=mainline,
        scheduler=scheduler,
        dispatch=dispatch,
    )

    return {
        "mainline": mainline,
        "scheduler": scheduler,
        "dispatch": dispatch,
        "coordination": coordination,
    }


def test_runtime_native_orchestrator_seal_full_stack(tmp_path):
    stack = build_orchestrator_stack(tmp_path)

    mainline = stack["mainline"]
    scheduler = stack["scheduler"]
    dispatch = stack["dispatch"]
    coordination = stack["coordination"]

    planner_node = coordination.register_node(
        runtime_id="planner-runtime",
        namespace="zero.orchestrator.planner",
        owner_id="planner-owner",
        source_session_id="planner-session",
        role="planner",
    )

    execution_node = coordination.register_node(
        runtime_id="orchestrator-seal-runtime",
        namespace="zero.orchestrator.execution",
        owner_id="orchestrator-owner",
        source_session_id="orchestrator-session",
        role="execution",
    )

    recovery_node = coordination.register_node(
        runtime_id="orchestrator-seal-runtime",
        namespace="zero.orchestrator.recovery",
        owner_id="orchestrator-owner",
        source_session_id="orchestrator-session",
        role="recovery",
    )

    rendezvous = coordination.open_rendezvous(
        name="orchestrator seal boot rendezvous",
        required_node_ids=[
            planner_node.node_id,
            execution_node.node_id,
            recovery_node.node_id,
        ],
    )

    coordination.join_rendezvous(rendezvous.rendezvous_id, planner_node.node_id)
    coordination.join_rendezvous(rendezvous.rendezvous_id, execution_node.node_id)
    joined = coordination.join_rendezvous(rendezvous.rendezvous_id, recovery_node.node_id)

    assert joined.status == "completed"

    item = scheduler.schedule_goal(
        goal="runtime-native orchestrator seal scheduled task",
        task_id="orchestrator-seal-task",
        ready_tick=1,
        priority=90,
        metadata={"seal": "orchestrator"},
    )

    failed_once = {"value": False}

    def runner(step, context):
        if step["name"] == "repairable" and not failed_once["value"]:
            failed_once["value"] = True
            return {
                "ok": False,
                "failed": True,
                "message": "planned orchestrator seal failure",
            }
        return {
            "ok": True,
            "name": step["name"],
        }

    dispatched = dispatch.dispatch_schedule_item(
        item,
        current_tick=2,
        planner_fn=lambda goal, context: {
            "summary": "orchestrator seal plan",
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
        step_runner=runner,
        resume_runner=lambda step, context: {
            "ok": True,
            "name": step["name"],
        },
    )

    assert dispatched.status == "completed"
    assert dispatched.schedule_id == item.schedule_id
    assert dispatched.task_id == "orchestrator-seal-task"
    assert dispatched.execution_id
    assert dispatched.continuation_ref["resume_step_index"] == 2
    assert dispatched.recovery_ref["recovery_ticket"]["status"] == "completed"

    cross_runtime = coordination.dispatch_between_nodes(
        source_node_id=planner_node.node_id,
        target_node_id=execution_node.node_id,
        goal="runtime-native orchestrator cross-runtime task",
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "cross-runtime"},
            ],
        },
        step_runner=lambda step, context: {
            "ok": True,
            "name": step["name"],
        },
        current_tick=3,
    )

    assert cross_runtime["ok"] is True
    assert cross_runtime["dispatch"]["status"] == "completed"

    recovery_signal = coordination.send_signal(
        source_node_id=execution_node.node_id,
        target_node_id=recovery_node.node_id,
        signal_type="recovery_request",
        payload={
            "task_id": "orchestrator-cross-runtime-recovery",
            "current_tick": 4,
        },
    )

    delivered_recovery = coordination.deliver_signal(recovery_signal.signal_id)

    assert delivered_recovery.status == "delivered"
    assert delivered_recovery.recovery_ref["recovery_ticket"]["source_session_id"] == "orchestrator-session"

    mainline_health = mainline.health()
    scheduler_health = scheduler.health()
    dispatch_health = dispatch.health()
    coordination_health = coordination.health()

    assert mainline_health["queue_tickets"] >= 2
    assert mainline_health["execution_records"] >= 2
    assert scheduler_health["items"] == 1
    assert dispatch_health["dispatches"] >= 2
    assert dispatch_health["execution_map_size"] >= 2
    assert coordination_health["nodes"] == 3
    assert coordination_health["signals"] >= 2
    assert coordination_health["rendezvous"] == 1

    lineage = mainline.orchestrator.lineage.lineage_for_ref("orchestrator-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}

    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "recovery" in node_types
    assert "runtime_replay" in node_types

    denied = mainline.ownership_fabric.authorize(
        runtime_id="orchestrator-seal-runtime",
        capability="execute",
        target="workspace/system/unsafe.py",
        owner_id="orchestrator-owner",
    )

    assert denied.decision == "deny"

    tick = mainline.supervisor_bridge.tick(current_tick=5).to_dict()

    assert tick["watchdog_lease_result"]["incident_count"] == 0


def test_runtime_native_orchestrator_seal_persistence_reload(tmp_path):
    stack = build_orchestrator_stack(tmp_path)

    mainline = stack["mainline"]
    scheduler = stack["scheduler"]
    dispatch = stack["dispatch"]
    coordination = stack["coordination"]

    node = coordination.register_node(
        runtime_id="orchestrator-seal-runtime",
        namespace="zero.orchestrator.reload",
        owner_id="orchestrator-owner",
        source_session_id="orchestrator-session",
        role="reload",
    )

    item = scheduler.schedule_goal(
        goal="orchestrator reload scheduled task",
        task_id="orchestrator-reload-task",
        ready_tick=1,
    )

    result = dispatch.dispatch_schedule_item(
        item,
        current_tick=2,
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "reload"},
            ],
        },
        step_runner=lambda step, context: {
            "ok": True,
            "name": step["name"],
        },
    )

    assert result.status == "completed"

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
    reloaded_coordination = RuntimeNativeMultiSessionCoordination.with_workspace(
        tmp_path / "coordination",
        mainline=reloaded_mainline,
        scheduler=reloaded_scheduler,
        dispatch=reloaded_dispatch,
    )

    reloaded_mainline.boot()

    assert reloaded_coordination.get_node(node.node_id).node_id == node.node_id
    assert reloaded_scheduler.get_item(item.schedule_id).schedule_id == item.schedule_id
    assert reloaded_dispatch.get_dispatch(result.dispatch_id).status == "completed"
    assert reloaded_mainline.health()["execution_records"] >= 1

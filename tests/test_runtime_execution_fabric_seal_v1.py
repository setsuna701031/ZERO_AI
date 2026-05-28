from __future__ import annotations

from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_session_lease import RuntimeSessionLeaseRegistry
from core.runtime.runtime_supervisor import RuntimeSupervisor
from core.runtime.runtime_supervisor_bridge import RuntimeSupervisorBridge
from core.runtime.runtime_watchdog import RuntimeWatchdog
from core.runtime.runtime_watchdog_lease_bridge import RuntimeWatchdogLeaseBridge


def test_runtime_execution_fabric_full_recovery_resume_mainline(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "recovery-execution-mainline",
            "replay_id": "replay-mainline",
        },
    )
    lease_registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path / "lease",
        default_ttl_ticks=5,
        zombie_after_ticks=20,
    )
    watchdog = RuntimeWatchdog.with_workspace(
        tmp_path / "watchdog",
        stall_after_ticks=3,
        dead_after_ticks=10,
    )
    watchdog_lease_bridge = RuntimeWatchdogLeaseBridge(
        lease_registry=lease_registry,
        watchdog=watchdog,
        orchestrator=None,
    )
    supervisor = RuntimeSupervisor.with_workspace(
        tmp_path / "supervisor",
        orchestrator=orchestrator,
        lease_registry=lease_registry,
    )
    supervisor_bridge = RuntimeSupervisorBridge.with_workspace(
        tmp_path / "supervisor_bridge",
        watchdog_lease_bridge=watchdog_lease_bridge,
        supervisor=supervisor,
        recovery_orchestrator=orchestrator,
    )
    execution_fabric = RuntimeExecutionFabric.with_workspace(
        tmp_path / "execution_fabric",
        recovery_orchestrator=orchestrator,
        supervisor=supervisor,
    )

    supervisor_bridge.register_session(
        "mainline-session",
        "owner-a",
        task_id="mainline-task",
        current_tick=1,
    )

    execution = execution_fabric.start_execution(
        source_session_id="mainline-session",
        task_id="mainline-task",
        steps=[
            {"type": "work", "name": "prepare"},
            {"type": "work", "name": "repairable"},
            {"type": "work", "name": "finish"},
        ],
    )

    execution_fabric.record_step_result(
        execution.execution_id,
        step_index=1,
        step={"type": "work", "name": "prepare"},
        result={"ok": True},
    )
    execution_fabric.record_step_result(
        execution.execution_id,
        step_index=2,
        step={"type": "work", "name": "repairable"},
        result={"ok": False, "failed": True, "message": "repairable failure"},
    )

    queued = execution_fabric.queue_recovery(
        execution.execution_id,
        current_tick=2,
        reason="mainline execution failed",
    )

    assert queued.status == "recovery_queued"
    assert queued.recovery_ticket["source_session_id"] == "mainline-session"

    continuation = execution_fabric.consume_recovery_and_build_continuation(
        execution.execution_id,
        current_tick=2,
    )

    assert continuation.resume_step_index == 2

    ran = []

    def runner(step, context):
        ran.append(step["name"])
        return {"ok": True, "name": step["name"]}

    completed = execution_fabric.resume_from_continuation(
        continuation.continuation_id,
        runner=runner,
    )

    assert completed.status == "completed"
    assert ran == ["finish"]
    assert completed.replay_ref["replay_id"] == "replay-mainline"

    lineage = orchestrator.lineage.lineage_for_ref("mainline-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}
    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "recovery" in node_types
    assert "runtime_replay" in node_types

    supervisor_bridge.heartbeat(
        "mainline-session",
        "owner-a",
        task_id="mainline-task",
        current_tick=3,
    )
    tick = supervisor_bridge.tick(current_tick=4).to_dict()
    assert tick["watchdog_lease_result"]["incident_count"] == 0

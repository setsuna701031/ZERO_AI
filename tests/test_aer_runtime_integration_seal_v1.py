from __future__ import annotations

from core.runtime.aer_runtime_integration import AERRuntimeIntegration
from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_ownership_isolation_fabric import (
    CAPABILITY_EXECUTE,
    CAPABILITY_READ,
    CAPABILITY_WRITE,
    RuntimeOwnershipIsolationFabric,
)
from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_session_lease import RuntimeSessionLeaseRegistry
from core.runtime.runtime_supervisor import RuntimeSupervisor
from core.runtime.runtime_supervisor_bridge import RuntimeSupervisorBridge
from core.runtime.runtime_transaction_fabric import RuntimeTransactionFabric
from core.runtime.runtime_watchdog import RuntimeWatchdog
from core.runtime.runtime_watchdog_lease_bridge import RuntimeWatchdogLeaseBridge


def test_aer_runtime_integration_full_core_mainline(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "aer-seal-recovery-execution",
            "replay_id": "aer-seal-replay",
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
        tmp_path / "execution",
        recovery_orchestrator=orchestrator,
        supervisor=supervisor,
    )
    transaction_fabric = RuntimeTransactionFabric.with_workspace(
        tmp_path / "transaction",
        recovery_orchestrator=orchestrator,
        execution_fabric=execution_fabric,
    )
    ownership_fabric = RuntimeOwnershipIsolationFabric.with_workspace(
        tmp_path / "ownership",
    )
    integration = AERRuntimeIntegration.with_workspace(
        tmp_path / "integration",
        recovery_orchestrator=orchestrator,
        execution_fabric=execution_fabric,
        transaction_fabric=transaction_fabric,
        ownership_fabric=ownership_fabric,
        supervisor_bridge=supervisor_bridge,
    )

    ownership_fabric.register_runtime(
        runtime_id="aer-runtime",
        namespace="zero.aer.integration",
        owner_id="aer-owner",
        session_ids=["aer-session"],
        capabilities=[CAPABILITY_READ, CAPABILITY_WRITE, CAPABILITY_EXECUTE],
        allowed_paths=["aer://task/", "workspace/aer/"],
    )

    supervisor_bridge.register_session(
        "aer-session",
        "aer-owner",
        task_id="aer-task",
        current_tick=1,
    )

    task = integration.run_recover_resume(
        goal="execute AER integrated task",
        source_session_id="aer-session",
        runtime_id="aer-runtime",
        metadata={"owner_id": "aer-owner"},
        planner_fn=lambda goal, context: {
            "summary": "AER seal plan",
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
        step_runner=lambda step, context: (
            {"ok": False, "failed": True, "message": "planned failure"}
            if step["name"] == "repairable"
            else {"ok": True, "name": step["name"]}
        ),
        resume_runner=lambda step, context: {"ok": True, "name": step["name"]},
        current_tick=2,
    )

    assert task.status == "failed"
    assert task.final_result["error"]
    assert task.execution_id

    execution = execution_fabric.get_execution(task.execution_id)
    assert execution.status != "completed"
    assert execution.replay_ref["replay_id"] == "aer-seal-replay"

    lineage = orchestrator.lineage.lineage_for_ref("aer-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}
    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "runtime_replay" in node_types

    supervisor_bridge.heartbeat(
        "aer-session",
        "aer-owner",
        task_id="aer-task",
        current_tick=3,
    )
    tick = supervisor_bridge.tick(current_tick=4).to_dict()
    assert tick["watchdog_lease_result"]["incident_count"] == 0

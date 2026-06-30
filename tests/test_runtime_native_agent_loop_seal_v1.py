from __future__ import annotations

from core.runtime.aer_runtime_integration import AERRuntimeIntegration
from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_native_agent_loop import RuntimeNativeAgentLoop
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
from core.runtime.runtime_watchdog import RuntimeWatchdog
from core.runtime.runtime_watchdog_lease_bridge import RuntimeWatchdogLeaseBridge
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def test_runtime_native_agent_loop_full_aer_mainline(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "native-loop-recovery-execution",
            "replay_id": "native-loop-replay",
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
    ownership = RuntimeOwnershipIsolationFabric.with_workspace(
        tmp_path / "ownership",
    )
    integration = AERRuntimeIntegration.with_workspace(
        tmp_path / "integration",
        recovery_orchestrator=orchestrator,
        execution_fabric=execution_fabric,
        ownership_fabric=ownership,
        supervisor_bridge=supervisor_bridge,
    )
    loop = RuntimeNativeAgentLoop.with_workspace(
        tmp_path / "loop",
        aer_integration=integration,
        supervisor_bridge=supervisor_bridge,
        ownership_fabric=ownership,
    )

    ownership.register_runtime(
        runtime_id="native-runtime",
        namespace="zero.native.loop",
        owner_id="native-owner",
        session_ids=["native-session"],
        capabilities=[CAPABILITY_READ, CAPABILITY_WRITE, CAPABILITY_EXECUTE],
        allowed_paths=["aer://task/"],
    )
    supervisor_bridge.register_session(
        "native-session",
        "native-owner",
        task_id="native-task",
        current_tick=1,
    )

    record = loop.create_loop(
        source_session_id="native-session",
        runtime_id="native-runtime",
        owner_id="native-owner",
        max_cycles=10,
    )

    completed = loop.run_goal(
        record.loop_id,
        goal="runtime native long chain task",
        planner_fn=lambda goal, context: {
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
        step_runner=lambda step, context: (
            {"ok": False, "failed": True, "message": "planned native failure"}
            if step["name"] == "repairable"
            else {"ok": True, "name": step["name"]}
        ),
        resume_runner=lambda step, context: {"ok": True, "name": step["name"]},
        current_tick=2,
    )

    assert completed.status == "completed"
    assert completed.task["status"] == "completed"
    assert completed.task["continuation_ref"]["resume_step_index"] == 2
    assert len(completed.cycles) == 3

    execution = execution_fabric.get_execution(completed.task["execution_id"])
    assert execution.status == "completed"
    assert execution.replay_ref["replay_id"] == "native-loop-replay"

    lineage = orchestrator.lineage.lineage_for_ref("native-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}
    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "runtime_replay" in node_types

    tick = supervisor_bridge.tick(current_tick=3).to_dict()
    assert tick["watchdog_lease_result"]["incident_count"] == 0

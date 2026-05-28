from __future__ import annotations

from core.runtime.aer_runtime_integration import AERRuntimeIntegration
from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_native_agent_loop import RuntimeNativeAgentLoop
from core.runtime.runtime_ownership_isolation_fabric import (
    AUTHORITY_ALLOW,
    AUTHORITY_DENY,
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


def build_native_core(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "native-core-recovery-execution",
            "replay_id": "native-core-replay",
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

    aer_integration = AERRuntimeIntegration.with_workspace(
        tmp_path / "aer_integration",
        recovery_orchestrator=orchestrator,
        execution_fabric=execution_fabric,
        transaction_fabric=transaction_fabric,
        ownership_fabric=ownership_fabric,
        supervisor_bridge=supervisor_bridge,
    )

    runtime_loop = RuntimeNativeAgentLoop.with_workspace(
        tmp_path / "runtime_loop",
        aer_integration=aer_integration,
        supervisor_bridge=supervisor_bridge,
        ownership_fabric=ownership_fabric,
    )

    return {
        "orchestrator": orchestrator,
        "lease_registry": lease_registry,
        "watchdog": watchdog,
        "watchdog_lease_bridge": watchdog_lease_bridge,
        "supervisor": supervisor,
        "supervisor_bridge": supervisor_bridge,
        "execution_fabric": execution_fabric,
        "transaction_fabric": transaction_fabric,
        "ownership_fabric": ownership_fabric,
        "aer_integration": aer_integration,
        "runtime_loop": runtime_loop,
    }


def test_runtime_native_core_seal_full_mainline(tmp_path):
    core = build_native_core(tmp_path)

    ownership = core["ownership_fabric"]
    supervisor_bridge = core["supervisor_bridge"]
    runtime_loop = core["runtime_loop"]
    execution_fabric = core["execution_fabric"]
    transaction_fabric = core["transaction_fabric"]
    orchestrator = core["orchestrator"]
    lease_registry = core["lease_registry"]
    watchdog = core["watchdog"]

    ownership.register_runtime(
        runtime_id="native-core-runtime",
        namespace="zero.native.core",
        owner_id="native-owner",
        session_ids=["native-core-session"],
        capabilities=[
            CAPABILITY_READ,
            CAPABILITY_WRITE,
            CAPABILITY_EXECUTE,
        ],
        allowed_paths=["aer://task/", "workspace/native/"],
        denied_paths=["workspace/system/"],
    )

    allowed = ownership.authorize(
        runtime_id="native-core-runtime",
        capability=CAPABILITY_EXECUTE,
        target="aer://task/native-core-bootstrap",
        owner_id="native-owner",
    )
    assert allowed.decision == AUTHORITY_ALLOW

    supervisor_bridge.register_session(
        "native-core-session",
        "native-owner",
        task_id="native-core-task",
        current_tick=1,
    )

    loop_record = runtime_loop.create_loop(
        source_session_id="native-core-session",
        runtime_id="native-core-runtime",
        owner_id="native-owner",
        max_cycles=20,
    )

    completed = runtime_loop.run_goal(
        loop_record.loop_id,
        goal="native core seal long-chain task",
        planner_fn=lambda goal, context: {
            "summary": "runtime-native seal plan",
            "steps": [
                {"type": "work", "name": "prepare"},
                {"type": "work", "name": "repairable"},
                {"type": "work", "name": "finish"},
            ],
        },
        step_runner=lambda step, context: (
            {"ok": False, "failed": True, "message": "planned native-core failure"}
            if step["name"] == "repairable"
            else {"ok": True, "name": step["name"]}
        ),
        resume_runner=lambda step, context: {"ok": True, "name": step["name"]},
        current_tick=2,
    )

    assert completed.status == "completed"
    assert len(completed.cycles) == 3
    assert completed.task["status"] == "completed"
    assert completed.task["continuation_ref"]["resume_step_index"] == 2

    execution = execution_fabric.get_execution(completed.task["execution_id"])
    assert execution.status == "completed"
    assert execution.replay_ref["replay_id"] == "native-core-replay"

    tx = transaction_fabric.begin_transaction(
        source_session_id="native-core-session",
        execution_id=execution.execution_id,
        task_id="native-core-task",
        before_snapshot={"files": {"workspace/native/core.py": "before"}},
        steps=[
            {"type": "write", "path": "workspace/native/core.py"},
            {"type": "verify", "path": "workspace/native/core.py"},
        ],
    )

    failed_tx = transaction_fabric.execute_transaction(
        tx.transaction_id,
        runner=lambda step, context: (
            {"ok": False, "failed": True, "message": "transaction verify failed"}
            if step.action_type == "verify"
            else {"ok": True}
        ),
    )
    assert failed_tx.status == "failed"

    rolled_tx = transaction_fabric.rollback_transaction(
        tx.transaction_id,
        reason="native core seal transaction rollback",
    )
    assert rolled_tx.status == "rolled_back"
    assert rolled_tx.boundary.after_snapshot == {"files": {"workspace/native/core.py": "before"}}

    queued_tx = transaction_fabric.queue_recovery(
        tx.transaction_id,
        current_tick=3,
        reason="native core transaction recovery",
    )
    assert queued_tx.status == "recovery_queued"

    recovered_tx = transaction_fabric.consume_recovery_and_continue(
        tx.transaction_id,
        current_tick=3,
    )
    assert recovered_tx.status == "recovered"
    assert recovered_tx.recovery_result["recovery_result"]["replay_id"] == "native-core-replay"

    supervisor_bridge.heartbeat(
        "native-core-session",
        "native-owner",
        task_id="native-core-task",
        current_tick=4,
    )
    tick = supervisor_bridge.tick(current_tick=5).to_dict()
    assert tick["watchdog_lease_result"]["incident_count"] == 0
    assert tick["supervisor_cases"] == []
    assert tick["recovery_results"] == []

    denied = ownership.authorize(
        runtime_id="native-core-runtime",
        capability=CAPABILITY_EXECUTE,
        target="workspace/system/unsafe.py",
        owner_id="native-owner",
    )
    assert denied.decision == AUTHORITY_DENY

    quarantined = ownership.quarantine_runtime(
        "native-core-runtime",
        reason="native core seal quarantine",
        restricted_capabilities=[CAPABILITY_EXECUTE],
        blocked_sessions=["native-core-session"],
    )
    assert quarantined.status == "quarantined"

    post_quarantine = ownership.authorize(
        runtime_id="native-core-runtime",
        capability=CAPABILITY_EXECUTE,
        target="workspace/native/run.py",
        owner_id="native-owner",
    )
    assert post_quarantine.decision == AUTHORITY_DENY

    lineage = orchestrator.lineage.lineage_for_ref("native-core-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}
    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "recovery" in node_types
    assert "runtime_replay" in node_types

    assert lease_registry.get_session("native-core-session").last_heartbeat_tick == 4
    assert watchdog.get_session("native-core-session").last_heartbeat_tick == 4
    assert len(orchestrator.queue.list_tickets()) == 2
    assert all(ticket.status == "completed" for ticket in orchestrator.queue.list_tickets())


def test_runtime_native_core_seal_zombie_takeover_and_recovery_storm(tmp_path):
    core = build_native_core(tmp_path)

    orchestrator = core["orchestrator"]

    lease_registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path / "lease_zombie_storm",
        default_ttl_ticks=100,
        zombie_after_ticks=5,
    )
    watchdog = RuntimeWatchdog.with_workspace(
        tmp_path / "watchdog_zombie_storm",
        stall_after_ticks=3,
        dead_after_ticks=10,
    )
    watchdog_lease_bridge = RuntimeWatchdogLeaseBridge(
        lease_registry=lease_registry,
        watchdog=watchdog,
        orchestrator=None,
    )
    supervisor = RuntimeSupervisor.with_workspace(
        tmp_path / "supervisor_zombie_storm",
        orchestrator=orchestrator,
        lease_registry=lease_registry,
    )
    supervisor_bridge = RuntimeSupervisorBridge.with_workspace(
        tmp_path / "supervisor_bridge_zombie_storm",
        watchdog_lease_bridge=watchdog_lease_bridge,
        supervisor=supervisor,
        recovery_orchestrator=orchestrator,
    )

    for index in range(4):
        supervisor_bridge.register_session(
            f"native-zombie-{index}",
            f"owner-{index}",
            task_id=f"zombie-task-{index}",
            current_tick=1,
        )

    result = supervisor_bridge.tick(current_tick=6).to_dict()

    assert result["watchdog_lease_result"]["incident_count"] == 4
    assert len(result["supervisor_cases"]) == 4
    assert all(case["status"] == "takeover_completed" for case in result["supervisor_cases"])

    for index in range(4):
        session = lease_registry.get_session(f"native-zombie-{index}")
        assert session.owner_id == "runtime-supervisor"
        assert session.takeover_count == 1


def test_runtime_native_core_seal_persistence_reload(tmp_path):
    core = build_native_core(tmp_path)

    core["ownership_fabric"].register_runtime(
        runtime_id="reload-native-runtime",
        namespace="zero.native.reload",
        owner_id="reload-owner",
        session_ids=["reload-native-session"],
        capabilities=[CAPABILITY_READ, CAPABILITY_EXECUTE],
        allowed_paths=["aer://task/"],
    )

    core["supervisor_bridge"].register_session(
        "reload-native-session",
        "reload-owner",
        task_id="reload-native-task",
        current_tick=1,
    )

    loop = core["runtime_loop"].create_loop(
        source_session_id="reload-native-session",
        runtime_id="reload-native-runtime",
        owner_id="reload-owner",
    )

    completed = core["runtime_loop"].run_goal(
        loop.loop_id,
        goal="reload native loop",
        planner_fn=lambda goal, context: {"steps": [{"type": "work", "name": "done"}]},
        step_runner=lambda step, context: {"ok": True},
        current_tick=1,
    )

    assert completed.status == "completed"

    reloaded_orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {"ok": True, "status": "completed"},
    )
    reloaded_lease = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path / "lease",
        default_ttl_ticks=5,
        zombie_after_ticks=20,
    )
    reloaded_watchdog = RuntimeWatchdog.with_workspace(
        tmp_path / "watchdog",
        stall_after_ticks=3,
        dead_after_ticks=10,
    )
    reloaded_supervisor = RuntimeSupervisor.with_workspace(
        tmp_path / "supervisor",
        orchestrator=reloaded_orchestrator,
        lease_registry=reloaded_lease,
    )
    reloaded_supervisor_bridge = RuntimeSupervisorBridge.with_workspace(
        tmp_path / "supervisor_bridge",
        watchdog_lease_bridge=RuntimeWatchdogLeaseBridge(
            lease_registry=reloaded_lease,
            watchdog=reloaded_watchdog,
            orchestrator=None,
        ),
        supervisor=reloaded_supervisor,
        recovery_orchestrator=reloaded_orchestrator,
    )
    reloaded_execution = RuntimeExecutionFabric.with_workspace(
        tmp_path / "execution",
        recovery_orchestrator=reloaded_orchestrator,
        supervisor=reloaded_supervisor,
    )
    reloaded_ownership = RuntimeOwnershipIsolationFabric.with_workspace(
        tmp_path / "ownership",
    )
    reloaded_integration = AERRuntimeIntegration.with_workspace(
        tmp_path / "aer_integration",
        recovery_orchestrator=reloaded_orchestrator,
        execution_fabric=reloaded_execution,
        ownership_fabric=reloaded_ownership,
        supervisor_bridge=reloaded_supervisor_bridge,
    )
    reloaded_loop = RuntimeNativeAgentLoop.with_workspace(
        tmp_path / "runtime_loop",
        aer_integration=reloaded_integration,
        supervisor_bridge=reloaded_supervisor_bridge,
        ownership_fabric=reloaded_ownership,
    )

    assert reloaded_loop.get_loop(loop.loop_id).status == "completed"
    assert reloaded_lease.get_session("reload-native-session").session_id == "reload-native-session"
    assert reloaded_watchdog.get_session("reload-native-session").session_id == "reload-native-session"
    assert reloaded_ownership.get_runtime("reload-native-runtime").runtime_id == "reload-native-runtime"

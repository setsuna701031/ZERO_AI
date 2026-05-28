from __future__ import annotations

from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
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


def build_core(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "core-seal-recovery-exec",
            "replay_id": "core-seal-replay",
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

    transaction_fabric = RuntimeTransactionFabric.with_workspace(
        tmp_path / "transaction_fabric",
        recovery_orchestrator=orchestrator,
        execution_fabric=execution_fabric,
    )

    ownership_fabric = RuntimeOwnershipIsolationFabric.with_workspace(
        tmp_path / "ownership_fabric",
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
    }


def test_runtime_core_seal_full_aer_mainline(tmp_path):
    core = build_core(tmp_path)

    orchestrator = core["orchestrator"]
    lease_registry = core["lease_registry"]
    watchdog = core["watchdog"]
    supervisor = core["supervisor"]
    supervisor_bridge = core["supervisor_bridge"]
    execution_fabric = core["execution_fabric"]
    transaction_fabric = core["transaction_fabric"]
    ownership_fabric = core["ownership_fabric"]

    ownership = ownership_fabric.register_runtime(
        runtime_id="core-runtime",
        namespace="zero.aer.core",
        owner_id="core-owner",
        session_ids=["core-session"],
        capabilities=[
            CAPABILITY_READ,
            CAPABILITY_WRITE,
            CAPABILITY_EXECUTE,
        ],
        allowed_paths=["workspace/core/"],
        denied_paths=["workspace/system/"],
    )

    assert ownership.runtime_id == "core-runtime"

    allowed = ownership_fabric.authorize(
        runtime_id="core-runtime",
        capability=CAPABILITY_WRITE,
        target="workspace/core/output.txt",
        owner_id="core-owner",
    )
    assert allowed.decision == AUTHORITY_ALLOW

    supervisor_bridge.register_session(
        "core-session",
        "core-owner",
        task_id="core-task",
        current_tick=1,
    )

    execution = execution_fabric.start_execution(
        source_session_id="core-session",
        task_id="core-task",
        steps=[
            {"type": "transaction", "name": "atomic-change"},
            {"type": "work", "name": "post-recovery-finish"},
        ],
    )

    transaction = transaction_fabric.begin_transaction(
        source_session_id="core-session",
        execution_id=execution.execution_id,
        task_id="core-task",
        before_snapshot={"files": {"workspace/core/target.py": "before"}},
        steps=[
            {"type": "write", "path": "workspace/core/target.py"},
            {"type": "verify", "path": "workspace/core/target.py"},
        ],
    )

    failed_transaction = transaction_fabric.execute_transaction(
        transaction.transaction_id,
        runner=lambda step, context: (
            {"ok": False, "failed": True, "message": "verification failed"}
            if step.action_type == "verify"
            else {"ok": True}
        ),
    )

    assert failed_transaction.status == "failed"
    assert failed_transaction.boundary.status == "broken"

    rolled_back = transaction_fabric.rollback_transaction(
        transaction.transaction_id,
        reason="core seal verification failed",
    )

    assert rolled_back.status == "rolled_back"
    assert rolled_back.boundary.after_snapshot == {
        "files": {"workspace/core/target.py": "before"}
    }

    queued_transaction = transaction_fabric.queue_recovery(
        transaction.transaction_id,
        current_tick=2,
        reason="transaction rollback requires recovery",
    )

    assert queued_transaction.status == "recovery_queued"
    assert queued_transaction.recovery_ticket["source_session_id"] == "core-session"

    recovered_transaction = transaction_fabric.consume_recovery_and_continue(
        transaction.transaction_id,
        current_tick=2,
    )

    assert recovered_transaction.status == "recovered"
    assert recovered_transaction.recovery_result["recovery_result"]["replay_id"] == "core-seal-replay"
    assert recovered_transaction.continuation_ref["status"] == "ready"

    execution_fabric.record_step_result(
        execution.execution_id,
        step_index=1,
        step={"type": "transaction", "name": "atomic-change"},
        result={
            "ok": True,
            "transaction_id": transaction.transaction_id,
            "transaction_status": recovered_transaction.status,
        },
    )

    execution_fabric.record_step_result(
        execution.execution_id,
        step_index=2,
        step={"type": "work", "name": "post-recovery-finish"},
        result={"ok": True, "message": "finished"},
    )

    completed_execution = execution_fabric.complete_execution(
        execution.execution_id,
        result={"ok": True, "final_answer": "runtime core seal completed"},
    )

    assert completed_execution.status == "completed"

    supervisor_bridge.heartbeat(
        "core-session",
        "core-owner",
        task_id="core-task",
        current_tick=3,
    )

    bridge_tick = supervisor_bridge.tick(current_tick=4).to_dict()

    assert bridge_tick["watchdog_lease_result"]["incident_count"] == 0
    assert bridge_tick["supervisor_cases"] == []
    assert bridge_tick["recovery_results"] == []

    blocked = ownership_fabric.authorize(
        runtime_id="core-runtime",
        capability=CAPABILITY_EXECUTE,
        target="workspace/system/unsafe.py",
        owner_id="core-owner",
    )

    assert blocked.decision == AUTHORITY_DENY

    quarantined = ownership_fabric.quarantine_runtime(
        "core-runtime",
        reason="core seal quarantine check",
        restricted_capabilities=[CAPABILITY_EXECUTE],
        blocked_sessions=["core-session"],
    )

    assert quarantined.status == "quarantined"

    post_quarantine = ownership_fabric.authorize(
        runtime_id="core-runtime",
        capability=CAPABILITY_EXECUTE,
        target="workspace/core/run.py",
        owner_id="core-owner",
    )

    assert post_quarantine.decision == AUTHORITY_DENY

    lineage = orchestrator.lineage.lineage_for_ref("core-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}

    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "recovery" in node_types
    assert "runtime_replay" in node_types

    assert lease_registry.get_session("core-session").last_heartbeat_tick == 3
    assert watchdog.get_session("core-session").last_heartbeat_tick == 3
    assert len(supervisor.list_cases()) == 0
    assert len(orchestrator.queue.list_tickets()) == 1
    assert orchestrator.queue.list_tickets()[0].status == "completed"


def test_runtime_core_seal_zombie_supervisor_takeover_path(tmp_path):
    core = build_core(tmp_path)

    lease_registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path / "lease_zombie",
        default_ttl_ticks=100,
        zombie_after_ticks=5,
    )
    watchdog = RuntimeWatchdog.with_workspace(
        tmp_path / "watchdog_zombie",
        stall_after_ticks=3,
        dead_after_ticks=10,
    )
    watchdog_lease_bridge = RuntimeWatchdogLeaseBridge(
        lease_registry=lease_registry,
        watchdog=watchdog,
        orchestrator=None,
    )
    supervisor = RuntimeSupervisor.with_workspace(
        tmp_path / "supervisor_zombie",
        orchestrator=core["orchestrator"],
        lease_registry=lease_registry,
    )
    supervisor_bridge = RuntimeSupervisorBridge.with_workspace(
        tmp_path / "supervisor_bridge_zombie",
        watchdog_lease_bridge=watchdog_lease_bridge,
        supervisor=supervisor,
        recovery_orchestrator=core["orchestrator"],
    )

    supervisor_bridge.register_session(
        "zombie-session",
        "owner-a",
        task_id="zombie-task",
        current_tick=1,
    )

    result = supervisor_bridge.tick(current_tick=6).to_dict()

    assert result["watchdog_lease_result"]["incident_count"] == 1
    assert result["watchdog_lease_result"]["incidents"][0]["incident_type"] == "runtime_session_zombie"
    assert result["supervisor_cases"][0]["decision"] == "takeover"
    assert result["supervisor_cases"][0]["status"] == "takeover_completed"
    assert lease_registry.get_session("zombie-session").owner_id == "runtime-supervisor"


def test_runtime_core_seal_persistence_reload(tmp_path):
    core = build_core(tmp_path)

    core["supervisor_bridge"].register_session(
        "reload-session",
        "reload-owner",
        task_id="reload-task",
        current_tick=1,
    )

    execution = core["execution_fabric"].start_execution(
        source_session_id="reload-session",
        task_id="reload-task",
        steps=[{"type": "noop"}],
    )

    core["execution_fabric"].record_step_result(
        execution.execution_id,
        step_index=1,
        step={"type": "noop"},
        result={"ok": True},
    )

    core["ownership_fabric"].register_runtime(
        runtime_id="reload-runtime",
        namespace="zero.reload",
        owner_id="reload-owner",
        session_ids=["reload-session"],
        capabilities=[CAPABILITY_READ],
    )

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
        tmp_path / "execution_fabric",
        recovery_orchestrator=reloaded_orchestrator,
        supervisor=reloaded_supervisor,
    )
    reloaded_ownership = RuntimeOwnershipIsolationFabric.with_workspace(
        tmp_path / "ownership_fabric",
    )

    assert reloaded_lease.get_session("reload-session").session_id == "reload-session"
    assert reloaded_watchdog.get_session("reload-session").session_id == "reload-session"
    assert reloaded_execution.get_execution(execution.execution_id).execution_id == execution.execution_id
    assert reloaded_ownership.get_runtime("reload-runtime").runtime_id == "reload-runtime"
    assert reloaded_supervisor_bridge.latest_result() is None

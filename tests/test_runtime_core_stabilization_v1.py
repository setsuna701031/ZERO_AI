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


def build_stabilization_core(tmp_path, *, ttl=5, zombie_after=20):
    recovery_calls = []

    def recovery_runner(payload):
        recovery_calls.append(payload)
        return {
            "ok": True,
            "status": "completed",
            "execution_id": f"stabilization-recovery-{len(recovery_calls)}",
            "replay_id": f"stabilization-replay-{len(recovery_calls)}",
        }

    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=recovery_runner,
        max_attempts=3,
    )

    lease_registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path / "lease",
        default_ttl_ticks=ttl,
        zombie_after_ticks=zombie_after,
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
        "recovery_calls": recovery_calls,
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


def test_runtime_core_stabilization_multiple_sessions_recover_without_cross_contamination(tmp_path):
    core = build_stabilization_core(tmp_path, ttl=2, zombie_after=20)
    bridge = core["supervisor_bridge"]
    orchestrator = core["orchestrator"]

    for index in range(5):
        bridge.register_session(
            f"stable-session-{index}",
            f"owner-{index}",
            task_id=f"task-{index}",
            current_tick=1,
        )

    result = bridge.tick(current_tick=4).to_dict()

    assert result["watchdog_lease_result"]["incident_count"] == 5
    assert len(result["supervisor_cases"]) == 5
    assert len(result["recovery_results"]) == 5

    tickets = orchestrator.queue.list_tickets()
    assert len(tickets) == 5
    assert all(ticket.status == "completed" for ticket in tickets)

    for index in range(5):
        lineage = orchestrator.lineage.lineage_for_ref(f"stable-session-{index}")
        refs = {node["ref_id"] for node in lineage["nodes"]}
        assert f"stable-session-{index}" in refs
        assert all(
            f"stable-session-{other}" not in refs
            for other in range(5)
            if other != index
        )


def test_runtime_core_stabilization_recovery_storm_is_bounded_by_queue_limit(tmp_path):
    core = build_stabilization_core(tmp_path, ttl=2, zombie_after=20)
    bridge = core["supervisor_bridge"]
    orchestrator = core["orchestrator"]

    for index in range(8):
        bridge.register_session(
            f"storm-session-{index}",
            f"owner-{index}",
            task_id=f"storm-task-{index}",
            current_tick=1,
        )

    first = bridge.tick(current_tick=4, run_recovery_queue=False).to_dict()

    assert len(first["supervisor_cases"]) == 8
    assert first["recovery_results"] == []
    assert len(orchestrator.queue.peek_ready(current_tick=4, limit=20)) == 8

    consumed_a = orchestrator.consume_ready(current_tick=4, limit=3)
    consumed_b = orchestrator.consume_ready(current_tick=4, limit=3)
    consumed_c = orchestrator.consume_ready(current_tick=4, limit=3)

    assert len(consumed_a) == 3
    assert len(consumed_b) == 3
    assert len(consumed_c) == 2
    assert all(item.ok for item in consumed_a + consumed_b + consumed_c)


def test_runtime_core_stabilization_transaction_rollback_repeatable(tmp_path):
    core = build_stabilization_core(tmp_path)
    transaction_fabric = core["transaction_fabric"]

    for index in range(3):
        tx = transaction_fabric.begin_transaction(
            source_session_id=f"tx-session-{index}",
            execution_id=f"execution-{index}",
            task_id=f"task-{index}",
            before_snapshot={"counter": index},
            steps=[
                {"type": "write", "index": index},
                {"type": "verify", "index": index},
            ],
        )

        failed = transaction_fabric.execute_transaction(
            tx.transaction_id,
            runner=lambda step, context: (
                {"ok": False, "failed": True, "message": "verify failed"}
                if step.action_type == "verify"
                else {"ok": True}
            ),
        )
        assert failed.status == "failed"

        rolled = transaction_fabric.rollback_transaction(
            tx.transaction_id,
            reason="repeatable rollback",
        )
        assert rolled.status == "rolled_back"
        assert rolled.boundary.after_snapshot == {"counter": index}


def test_runtime_core_stabilization_ownership_quarantine_blocks_after_previous_allow(tmp_path):
    core = build_stabilization_core(tmp_path)
    ownership = core["ownership_fabric"]

    ownership.register_runtime(
        runtime_id="stability-runtime",
        namespace="zero.stability",
        owner_id="owner-a",
        capabilities=[CAPABILITY_READ, CAPABILITY_WRITE, CAPABILITY_EXECUTE],
        allowed_paths=["workspace/stability/"],
    )

    before = ownership.authorize(
        runtime_id="stability-runtime",
        capability=CAPABILITY_EXECUTE,
        target="workspace/stability/run.py",
        owner_id="owner-a",
    )
    assert before.decision == AUTHORITY_ALLOW

    ownership.quarantine_runtime(
        "stability-runtime",
        reason="stability quarantine",
        restricted_capabilities=[CAPABILITY_EXECUTE],
        blocked_sessions=["stability-session"],
    )

    after = ownership.authorize(
        runtime_id="stability-runtime",
        capability=CAPABILITY_EXECUTE,
        target="workspace/stability/run.py",
        owner_id="owner-a",
    )
    assert after.decision == AUTHORITY_DENY


def test_runtime_core_stabilization_persistence_survives_full_reload_after_storm(tmp_path):
    core = build_stabilization_core(tmp_path, ttl=2, zombie_after=20)
    bridge = core["supervisor_bridge"]

    for index in range(4):
        bridge.register_session(
            f"reload-storm-session-{index}",
            f"owner-{index}",
            task_id=f"reload-storm-task-{index}",
            current_tick=1,
        )

    bridge.tick(current_tick=4).to_dict()

    reloaded_orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {"ok": True, "status": "completed"},
    )
    reloaded_lease = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path / "lease",
        default_ttl_ticks=2,
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
    reloaded_bridge = RuntimeSupervisorBridge.with_workspace(
        tmp_path / "supervisor_bridge",
        watchdog_lease_bridge=RuntimeWatchdogLeaseBridge(
            lease_registry=reloaded_lease,
            watchdog=reloaded_watchdog,
            orchestrator=None,
        ),
        supervisor=reloaded_supervisor,
        recovery_orchestrator=reloaded_orchestrator,
    )

    assert len(reloaded_orchestrator.queue.list_tickets()) == 4
    assert all(ticket.status == "completed" for ticket in reloaded_orchestrator.queue.list_tickets())
    assert len(reloaded_supervisor.list_cases()) == 4
    assert reloaded_bridge.latest_result() is not None

    for index in range(4):
        assert reloaded_lease.get_session(f"reload-storm-session-{index}").session_id == f"reload-storm-session-{index}"
        assert reloaded_watchdog.get_session(f"reload-storm-session-{index}").session_id == f"reload-storm-session-{index}"


def test_runtime_core_stabilization_no_false_positive_after_regular_heartbeats(tmp_path):
    core = build_stabilization_core(tmp_path, ttl=5, zombie_after=20)
    bridge = core["supervisor_bridge"]

    bridge.register_session(
        "heartbeat-session",
        "heartbeat-owner",
        task_id="heartbeat-task",
        current_tick=1,
    )

    for tick in range(2, 8):
        bridge.heartbeat(
            "heartbeat-session",
            "heartbeat-owner",
            task_id="heartbeat-task",
            current_tick=tick,
        )
        result = bridge.tick(current_tick=tick).to_dict()
        assert result["watchdog_lease_result"]["incident_count"] == 0
        assert result["supervisor_cases"] == []
        assert result["recovery_results"] == []


def test_runtime_core_stabilization_recovery_failure_escalates_after_bounded_retries(tmp_path):
    failing_orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "failing_recovery",
        runner=lambda payload: {"ok": False, "failed": True, "message": "still broken"},
        max_attempts=2,
    )

    ticket = failing_orchestrator.queue.enqueue(
        recovery_id="bounded-recovery",
        source_session_id="bounded-session",
        incident_id="bounded-incident",
        task_id="bounded-task",
        current_tick=1,
        max_attempts=2,
    )

    first = failing_orchestrator.run_ticket(ticket.ticket_id, current_tick=1).to_dict()
    assert first["status"] == "queued"

    second = failing_orchestrator.run_ticket(ticket.ticket_id, current_tick=2).to_dict()
    assert second["status"] == "escalated"
    assert second["supervisor_handoff"]["recovery_id"] == "bounded-recovery"

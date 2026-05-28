from __future__ import annotations

from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_session_lease import (
    RuntimeSessionLeaseRegistry,
    SESSION_STATUS_TRANSFERRED,
)
from core.runtime.runtime_supervisor import RuntimeSupervisor
from core.runtime.runtime_supervisor_bridge import RuntimeSupervisorBridge
from core.runtime.runtime_watchdog import RuntimeWatchdog
from core.runtime.runtime_watchdog_lease_bridge import RuntimeWatchdogLeaseBridge


def build_runtime_fabric(tmp_path, *, ttl=2, zombie_after=20):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "seal-execution",
            "replay_id": "seal-replay",
        },
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
    return {
        "orchestrator": orchestrator,
        "lease_registry": lease_registry,
        "watchdog": watchdog,
        "watchdog_lease_bridge": watchdog_lease_bridge,
        "supervisor": supervisor,
        "supervisor_bridge": supervisor_bridge,
    }


def test_runtime_fabric_seal_recoverable_lease_expiry_mainline(tmp_path):
    fabric = build_runtime_fabric(tmp_path, ttl=2, zombie_after=20)
    bridge = fabric["supervisor_bridge"]
    orchestrator = fabric["orchestrator"]
    lease_registry = fabric["lease_registry"]
    supervisor = fabric["supervisor"]

    registered = bridge.register_session(
        "seal-session-1",
        "owner-a",
        task_id="seal-task-1",
        current_tick=1,
    )

    assert registered["session"]["session_id"] == "seal-session-1"
    assert registered["lease"]["owner_id"] == "owner-a"

    result = bridge.tick(current_tick=4).to_dict()

    assert result["ok"] is True
    assert result["watchdog_lease_result"]["incident_count"] == 1
    assert result["watchdog_lease_result"]["incidents"][0]["incident_type"] == "runtime_session_lease_expired"

    assert len(result["supervisor_cases"]) == 1
    case = result["supervisor_cases"][0]
    assert case["decision"] == "recover"
    assert case["status"] == "recovery_queued"
    assert case["recovery_ticket"]["source_session_id"] == "seal-session-1"

    assert len(result["recovery_results"]) == 1
    recovery = result["recovery_results"][0]
    assert recovery["ok"] is True
    assert recovery["status"] == "completed"
    assert recovery["recovery_result"]["replay_id"] == "seal-replay"

    queue_tickets = orchestrator.queue.list_tickets()
    assert len(queue_tickets) == 1
    assert queue_tickets[0].status == "completed"

    lineage = orchestrator.lineage.lineage_for_ref("seal-session-1")
    node_types = {node["node_type"] for node in lineage["nodes"]}
    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "recovery" in node_types
    assert "runtime_replay" in node_types

    assert lease_registry.get_session("seal-session-1").status == "expired"
    assert len(supervisor.list_cases()) == 1


def test_runtime_fabric_seal_zombie_takeover_mainline(tmp_path):
    fabric = build_runtime_fabric(tmp_path, ttl=100, zombie_after=5)
    bridge = fabric["supervisor_bridge"]
    lease_registry = fabric["lease_registry"]
    supervisor = fabric["supervisor"]

    bridge.register_session(
        "seal-session-2",
        "owner-a",
        task_id="seal-task-2",
        current_tick=1,
    )

    result = bridge.tick(current_tick=6).to_dict()

    assert result["ok"] is True
    assert result["watchdog_lease_result"]["incident_count"] == 1
    assert result["watchdog_lease_result"]["incidents"][0]["incident_type"] == "runtime_session_zombie"

    assert len(result["supervisor_cases"]) == 1
    case = result["supervisor_cases"][0]
    assert case["decision"] == "takeover"
    assert case["status"] == "takeover_completed"
    assert case["takeover_lease"]["owner_id"] == "runtime-supervisor"

    session = lease_registry.get_session("seal-session-2")
    assert session.owner_id == "runtime-supervisor"
    assert session.status == SESSION_STATUS_TRANSFERRED
    assert session.takeover_count == 1

    assert len(supervisor.list_cases()) == 1
    assert result["recovery_results"] == []


def test_runtime_fabric_seal_critical_freeze_escalation(tmp_path):
    fabric = build_runtime_fabric(tmp_path)
    supervisor = fabric["supervisor"]

    case = supervisor.process_incident(
        {
            "incident_id": "seal-critical-incident",
            "incident_type": "runtime_integrity_mismatch",
            "source_session_id": "seal-session-3",
            "task_id": "seal-task-3",
        },
        current_tick=10,
    )

    assert case.decision == "freeze"
    assert case.status == "escalated"
    assert case.freeze_record["source_session_id"] == "seal-session-3"
    assert case.metadata["escalated_tick"] == 10


def test_runtime_fabric_seal_heartbeat_prevents_false_positive(tmp_path):
    fabric = build_runtime_fabric(tmp_path, ttl=5, zombie_after=10)
    bridge = fabric["supervisor_bridge"]
    lease_registry = fabric["lease_registry"]
    watchdog = fabric["watchdog"]

    bridge.register_session(
        "seal-session-4",
        "owner-a",
        task_id="seal-task-4",
        current_tick=1,
    )
    bridge.heartbeat(
        "seal-session-4",
        "owner-a",
        task_id="seal-task-4",
        current_tick=4,
    )

    result = bridge.tick(current_tick=5).to_dict()

    assert result["watchdog_lease_result"]["incident_count"] == 0
    assert result["supervisor_cases"] == []
    assert result["recovery_results"] == []

    assert lease_registry.get_session("seal-session-4").last_heartbeat_tick == 4
    assert watchdog.get_session("seal-session-4").last_heartbeat_tick == 4


def test_runtime_fabric_seal_persistence_reload(tmp_path):
    fabric = build_runtime_fabric(tmp_path, ttl=2, zombie_after=20)
    bridge = fabric["supervisor_bridge"]
    orchestrator = fabric["orchestrator"]
    lease_registry = fabric["lease_registry"]
    supervisor = fabric["supervisor"]

    bridge.register_session(
        "seal-session-5",
        "owner-a",
        task_id="seal-task-5",
        current_tick=1,
    )
    first = bridge.tick(current_tick=4).to_dict()

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
    reloaded_watchdog_lease_bridge = RuntimeWatchdogLeaseBridge(
        lease_registry=reloaded_lease,
        watchdog=reloaded_watchdog,
    )
    reloaded_supervisor = RuntimeSupervisor.with_workspace(
        tmp_path / "supervisor",
        orchestrator=reloaded_orchestrator,
        lease_registry=reloaded_lease,
    )
    reloaded_bridge = RuntimeSupervisorBridge.with_workspace(
        tmp_path / "supervisor_bridge",
        watchdog_lease_bridge=reloaded_watchdog_lease_bridge,
        supervisor=reloaded_supervisor,
        recovery_orchestrator=reloaded_orchestrator,
    )

    latest = reloaded_bridge.latest_result()
    assert latest is not None
    assert latest.bridge_id == first["bridge_id"]

    assert len(reloaded_supervisor.list_cases()) == 1
    assert len(reloaded_orchestrator.queue.list_tickets()) == 1
    assert reloaded_lease.get_session("seal-session-5").session_id == "seal-session-5"


def test_runtime_fabric_seal_queue_can_be_left_for_later_consumption(tmp_path):
    fabric = build_runtime_fabric(tmp_path, ttl=2, zombie_after=20)
    bridge = fabric["supervisor_bridge"]
    orchestrator = fabric["orchestrator"]

    bridge.register_session(
        "seal-session-6",
        "owner-a",
        task_id="seal-task-6",
        current_tick=1,
    )

    result = bridge.tick(current_tick=4, run_recovery_queue=False).to_dict()

    assert result["supervisor_cases"][0]["status"] == "recovery_queued"
    assert result["recovery_results"] == []

    ready = orchestrator.queue.peek_ready(current_tick=4, limit=10)
    assert len(ready) == 1

    consumed = orchestrator.consume_ready(current_tick=4, limit=10)
    assert len(consumed) == 1
    assert consumed[0].ok is True
    assert orchestrator.queue.get_ticket(ready[0].ticket_id).status == "completed"

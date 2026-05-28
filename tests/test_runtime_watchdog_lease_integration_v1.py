from __future__ import annotations

from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_session_lease import (
    RuntimeSessionLeaseRegistry,
    SESSION_STATUS_TRANSFERRED,
)
from core.runtime.runtime_watchdog import RuntimeWatchdog
from core.runtime.runtime_watchdog_lease_bridge import (
    BRIDGE_INCIDENT_TYPE_LEASE_EXPIRED,
    BRIDGE_INCIDENT_TYPE_OWNERSHIP_MISMATCH,
    BRIDGE_INCIDENT_TYPE_SESSION_ZOMBIE,
    RuntimeWatchdogLeaseBridge,
)


def test_watchdog_lease_bridge_registers_and_heartbeats(tmp_path):
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
    bridge = RuntimeWatchdogLeaseBridge(
        lease_registry=lease_registry,
        watchdog=watchdog,
    )

    registered = bridge.register_session(
        "session-1",
        "owner-a",
        task_id="task-1",
        current_tick=1,
    )
    assert registered["lease"]["owner_id"] == "owner-a"

    heartbeat = bridge.heartbeat(
        "session-1",
        "owner-a",
        task_id="task-1",
        current_tick=3,
    )

    assert heartbeat["ok"] is True
    assert lease_registry.get_session("session-1").last_heartbeat_tick == 3
    assert watchdog.get_session("session-1").last_heartbeat_tick == 3


def test_watchdog_lease_bridge_emits_lease_expired_incident(tmp_path):
    lease_registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path / "lease",
        default_ttl_ticks=2,
        zombie_after_ticks=20,
    )
    bridge = RuntimeWatchdogLeaseBridge(lease_registry=lease_registry)

    bridge.register_session(
        "session-2",
        "owner-a",
        task_id="task-2",
        current_tick=1,
    )

    result = bridge.tick(current_tick=4, submit_to_recovery=False)

    assert result["incident_count"] == 1
    assert result["incidents"][0]["incident_type"] == BRIDGE_INCIDENT_TYPE_LEASE_EXPIRED
    assert result["incidents"][0]["source_session_id"] == "session-2"


def test_watchdog_lease_bridge_emits_zombie_incident(tmp_path):
    lease_registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path / "lease",
        default_ttl_ticks=100,
        zombie_after_ticks=5,
    )
    bridge = RuntimeWatchdogLeaseBridge(lease_registry=lease_registry)

    bridge.register_session(
        "session-3",
        "owner-a",
        task_id="task-3",
        current_tick=1,
    )

    result = bridge.tick(current_tick=6, submit_to_recovery=False)

    assert result["incident_count"] == 1
    assert result["incidents"][0]["incident_type"] == BRIDGE_INCIDENT_TYPE_SESSION_ZOMBIE


def test_watchdog_lease_bridge_submits_to_recovery_orchestrator(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {"ok": True, "status": "completed"},
    )
    lease_registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path / "lease",
        default_ttl_ticks=2,
        zombie_after_ticks=20,
    )
    bridge = RuntimeWatchdogLeaseBridge(
        lease_registry=lease_registry,
        orchestrator=orchestrator,
    )

    bridge.register_session(
        "session-4",
        "owner-a",
        task_id="task-4",
        current_tick=1,
    )

    result = bridge.tick(current_tick=4, submit_to_recovery=True)

    assert len(result["submitted_recovery_tickets"]) == 1
    assert result["submitted_recovery_tickets"][0]["source_session_id"] == "session-4"

    recovery_results = orchestrator.consume_ready(current_tick=4)
    assert len(recovery_results) == 1
    assert recovery_results[0].ok is True


def test_watchdog_lease_bridge_auto_takeover_zombie(tmp_path):
    lease_registry = RuntimeSessionLeaseRegistry.with_workspace(
        tmp_path / "lease",
        default_ttl_ticks=100,
        zombie_after_ticks=5,
    )
    bridge = RuntimeWatchdogLeaseBridge(
        lease_registry=lease_registry,
        auto_takeover_zombies=True,
        supervisor_owner_id="supervisor",
    )

    bridge.register_session(
        "session-5",
        "owner-a",
        task_id="task-5",
        current_tick=1,
    )

    result = bridge.tick(current_tick=6, submit_to_recovery=False)

    assert result["incident_count"] == 1
    session = lease_registry.get_session("session-5")
    assert session.owner_id == "supervisor"
    assert session.status == SESSION_STATUS_TRANSFERRED
    assert session.takeover_count == 1


def test_watchdog_lease_bridge_detects_ownership_mismatch(tmp_path):
    lease_registry = RuntimeSessionLeaseRegistry.with_workspace(tmp_path / "lease")
    bridge = RuntimeWatchdogLeaseBridge(lease_registry=lease_registry)

    bridge.register_session(
        "session-6",
        "owner-a",
        task_id="task-6",
        current_tick=1,
    )

    result = bridge.assert_owner(
        "session-6",
        "owner-b",
        current_tick=2,
        submit_to_recovery=False,
    )

    assert result["ok"] is False
    assert result["incident"]["incident_type"] == BRIDGE_INCIDENT_TYPE_OWNERSHIP_MISMATCH
    assert result["incident"]["metadata"]["expected_owner_id"] == "owner-b"
    assert result["incident"]["metadata"]["actual_owner_id"] == "owner-a"

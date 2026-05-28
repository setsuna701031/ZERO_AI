from __future__ import annotations

from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_session_lease import RuntimeSessionLeaseRegistry
from core.runtime.runtime_supervisor import RuntimeSupervisor
from core.runtime.runtime_supervisor_bridge import RuntimeSupervisorBridge
from core.runtime.runtime_watchdog import RuntimeWatchdog
from core.runtime.runtime_watchdog_lease_bridge import RuntimeWatchdogLeaseBridge


def _build_fabric(tmp_path, *, ttl=2, zombie_after=20):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {"ok": True, "status": "completed"},
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
    bridge = RuntimeSupervisorBridge.with_workspace(
        tmp_path / "bridge",
        watchdog_lease_bridge=watchdog_lease_bridge,
        supervisor=supervisor,
        recovery_orchestrator=orchestrator,
    )
    return bridge, orchestrator, lease_registry, watchdog, supervisor


def test_supervisor_bridge_routes_lease_expiry_to_supervisor_and_recovery(tmp_path):
    bridge, orchestrator, lease_registry, watchdog, supervisor = _build_fabric(
        tmp_path,
        ttl=2,
        zombie_after=20,
    )

    bridge.register_session(
        "session-1",
        "owner-a",
        task_id="task-1",
        current_tick=1,
    )

    result = bridge.tick(current_tick=4).to_dict()

    assert result["ok"] is True
    assert result["watchdog_lease_result"]["incident_count"] == 1
    assert result["supervisor_cases"][0]["status"] == "recovery_queued"
    assert result["recovery_results"][0]["ok"] is True


def test_supervisor_bridge_routes_zombie_to_takeover(tmp_path):
    bridge, orchestrator, lease_registry, watchdog, supervisor = _build_fabric(
        tmp_path,
        ttl=100,
        zombie_after=5,
    )

    bridge.register_session(
        "session-2",
        "owner-a",
        task_id="task-2",
        current_tick=1,
    )

    result = bridge.tick(current_tick=6).to_dict()

    assert result["watchdog_lease_result"]["incident_count"] == 1
    assert result["supervisor_cases"][0]["status"] == "takeover_completed"
    assert lease_registry.get_session("session-2").owner_id == "runtime-supervisor"


def test_supervisor_bridge_heartbeat_keeps_session_alive(tmp_path):
    bridge, orchestrator, lease_registry, watchdog, supervisor = _build_fabric(
        tmp_path,
        ttl=5,
        zombie_after=10,
    )

    bridge.register_session(
        "session-3",
        "owner-a",
        task_id="task-3",
        current_tick=1,
    )
    bridge.heartbeat(
        "session-3",
        "owner-a",
        task_id="task-3",
        current_tick=4,
    )

    result = bridge.tick(current_tick=5).to_dict()

    assert result["watchdog_lease_result"]["incident_count"] == 0
    assert result["supervisor_cases"] == []
    assert result["recovery_results"] == []


def test_supervisor_bridge_persists_results(tmp_path):
    bridge, orchestrator, lease_registry, watchdog, supervisor = _build_fabric(
        tmp_path,
        ttl=2,
        zombie_after=20,
    )

    bridge.register_session(
        "session-4",
        "owner-a",
        task_id="task-4",
        current_tick=1,
    )
    first = bridge.tick(current_tick=4).to_dict()

    reloaded = RuntimeSupervisorBridge.with_workspace(
        tmp_path / "bridge",
        watchdog_lease_bridge=bridge.watchdog_lease_bridge,
        supervisor=supervisor,
        recovery_orchestrator=orchestrator,
    )

    latest = reloaded.latest_result()
    assert latest is not None
    assert latest.bridge_id == first["bridge_id"]


def test_supervisor_bridge_can_disable_recovery_queue_consume(tmp_path):
    bridge, orchestrator, lease_registry, watchdog, supervisor = _build_fabric(
        tmp_path,
        ttl=2,
        zombie_after=20,
    )

    bridge.register_session(
        "session-5",
        "owner-a",
        task_id="task-5",
        current_tick=1,
    )

    result = bridge.tick(current_tick=4, run_recovery_queue=False).to_dict()

    assert result["supervisor_cases"][0]["status"] == "recovery_queued"
    assert result["recovery_results"] == []
    assert len(orchestrator.queue.peek_ready(current_tick=4, limit=10)) == 1

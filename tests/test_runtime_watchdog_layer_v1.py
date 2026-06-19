from __future__ import annotations

from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_watchdog import (
    WATCHDOG_INCIDENT_TYPE_DEAD,
    WATCHDOG_INCIDENT_TYPE_FROZEN,
    WATCHDOG_INCIDENT_TYPE_STALLED,
    RuntimeWatchdog,
)


def test_watchdog_detects_stalled_session(tmp_path):
    watchdog = RuntimeWatchdog.with_workspace(
        tmp_path,
        stall_after_ticks=3,
        dead_after_ticks=10,
    )

    watchdog.register_session(
        "session-1",
        task_id="task-1",
        current_tick=1,
        metadata={"runtime_session_id": "runtime-1", "source_session_id": "source-1"},
    )
    watchdog.heartbeat("session-1", task_id="task-1", current_tick=1)

    result = watchdog.tick(current_tick=4, submit_to_recovery=False)

    assert result["ok"] is True
    assert result["incident_count"] == 1
    assert result["incidents"][0]["incident_type"] == WATCHDOG_INCIDENT_TYPE_STALLED
    assert result["incidents"][0]["session_id"] == "session-1"
    assert result["incidents"][0]["runtime_session_id"] == "runtime-1"
    assert result["incidents"][0]["source_session_id"] == "source-1"


def test_watchdog_detects_dead_session(tmp_path):
    watchdog = RuntimeWatchdog.with_workspace(
        tmp_path,
        stall_after_ticks=3,
        dead_after_ticks=5,
    )

    watchdog.register_session("session-2", task_id="task-2", current_tick=1)
    watchdog.heartbeat("session-2", task_id="task-2", current_tick=1)

    result = watchdog.tick(current_tick=6, submit_to_recovery=False)

    assert result["incident_count"] == 1
    assert result["incidents"][0]["incident_type"] == WATCHDOG_INCIDENT_TYPE_DEAD


def test_watchdog_detects_frozen_session(tmp_path):
    watchdog = RuntimeWatchdog.with_workspace(
        tmp_path,
        stall_after_ticks=3,
        dead_after_ticks=10,
    )

    watchdog.register_session("session-3", task_id="task-3", current_tick=1)
    watchdog.heartbeat(
        "session-3",
        task_id="task-3",
        current_tick=2,
        payload={"runtime_frozen": True},
    )

    result = watchdog.tick(current_tick=2, submit_to_recovery=False)

    assert result["incident_count"] == 1
    assert result["incidents"][0]["incident_type"] == WATCHDOG_INCIDENT_TYPE_FROZEN


def test_watchdog_submits_incident_to_recovery_orchestrator(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {"ok": True, "status": "completed"},
    )
    watchdog = RuntimeWatchdog.with_workspace(
        tmp_path / "watchdog",
        stall_after_ticks=2,
        dead_after_ticks=10,
        orchestrator=orchestrator,
    )

    watchdog.register_session(
        "session-4",
        task_id="task-4",
        current_tick=1,
        metadata={"runtime_session_id": "runtime-4", "source_session_id": "source-4"},
    )
    watchdog.heartbeat("session-4", task_id="task-4", current_tick=1)

    result = watchdog.tick(current_tick=3, submit_to_recovery=True)

    assert result["incident_count"] == 1
    assert len(result["submitted_recovery_tickets"]) == 1
    assert result["submitted_recovery_tickets"][0]["source_session_id"] == "source-4"

    recovery_results = orchestrator.consume_ready(current_tick=3)
    assert len(recovery_results) == 1
    assert recovery_results[0].ok is True


def test_watchdog_does_not_emit_for_terminal_session(tmp_path):
    watchdog = RuntimeWatchdog.with_workspace(
        tmp_path,
        stall_after_ticks=2,
        dead_after_ticks=5,
    )

    watchdog.register_session("session-5", task_id="task-5", current_tick=1)
    watchdog.heartbeat("session-5", task_id="task-5", status="finished", current_tick=1)

    result = watchdog.tick(current_tick=100, submit_to_recovery=False)

    assert result["incident_count"] == 0

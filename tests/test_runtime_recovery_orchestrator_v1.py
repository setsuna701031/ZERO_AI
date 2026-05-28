from __future__ import annotations

from core.runtime.runtime_recovery_orchestrator import (
    RuntimeRecoveryBackoffPolicy,
    RuntimeRecoveryOrchestrator,
)
from core.runtime.runtime_recovery_queue import RECOVERY_TICKET_STATUS_COMPLETED, RECOVERY_TICKET_STATUS_ESCALATED


def test_recovery_orchestrator_completes_ready_ticket(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path,
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "exec-1",
            "replay_id": "replay-1",
        },
    )

    ticket = orchestrator.submit_incident(
        {
            "incident_id": "incident-1",
            "source_session_id": "session-1",
            "task_id": "task-1",
        },
        current_tick=1,
    )

    results = orchestrator.consume_ready(current_tick=1)

    assert len(results) == 1
    result = results[0].to_dict()
    assert result["ok"] is True
    assert result["status"] == RECOVERY_TICKET_STATUS_COMPLETED
    assert result["ticket"]["ticket_id"] == ticket.ticket_id
    assert result["recovery_result"]["replay_id"] == "replay-1"
    assert result["lineage"]["nodes"]["source_session"]["ref_id"] == "session-1"


def test_recovery_orchestrator_retries_then_escalates(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path,
        runner=lambda payload: {"ok": False, "failed": True, "message": "still failing"},
        max_attempts=2,
        backoff_policy=RuntimeRecoveryBackoffPolicy(base_delay_ticks=1, multiplier=1),
    )

    ticket = orchestrator.submit_incident(
        {
            "incident_id": "incident-2",
            "source_session_id": "session-2",
            "task_id": "task-2",
        },
        current_tick=1,
        max_attempts=2,
    )

    first = orchestrator.run_ticket(ticket.ticket_id, current_tick=1).to_dict()
    assert first["ok"] is False
    assert first["status"] == "queued"

    second = orchestrator.run_ticket(ticket.ticket_id, current_tick=2).to_dict()
    assert second["ok"] is False
    assert second["status"] == RECOVERY_TICKET_STATUS_ESCALATED
    assert second["supervisor_handoff"]["recovery_id"] == ticket.recovery_id
    assert second["ticket"]["metadata"]["supervisor_handoff"]["handoff_id"]


def test_recovery_orchestrator_requires_review_escalates(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path,
        runner=lambda payload: {"ok": False, "requires_review": True, "message": "operator review required"},
    )

    ticket = orchestrator.submit_incident(
        {
            "incident_id": "incident-3",
            "source_session_id": "session-3",
            "task_id": "task-3",
        },
        current_tick=1,
    )

    result = orchestrator.run_ticket(ticket.ticket_id, current_tick=1).to_dict()

    assert result["status"] == RECOVERY_TICKET_STATUS_ESCALATED
    assert result["supervisor_handoff"]["reason"] == "recovery requires supervisor review"

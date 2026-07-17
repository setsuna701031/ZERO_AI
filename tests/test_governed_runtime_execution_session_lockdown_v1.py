from __future__ import annotations

from core.runtime.governed_runtime_execution_session import (
    SESSION_BLOCKED,
    build_governed_runtime_lockdown_session_report,
    escalate_runtime_freeze_to_governed_session,
    validate_governed_runtime_execution_session_report,
)


def test_runtime_freeze_escalates_to_blocked_session() -> None:
    report = build_governed_runtime_lockdown_session_report(
        freeze_decision={
            "runtime_frozen": True,
            "denied": True,
            "reason": "rollback verification mismatch",
            "freeze_id": "freeze-001",
        },
        previous_session_state="running",
        source_execution_id="execution-001",
        source_gateway_id="gateway-001",
        source_boundary_id="boundary-001",
    )

    assert report["session_state"] == SESSION_BLOCKED
    assert report["continuation_contract"]["can_continue"] is False
    assert report["continuation_contract"]["continuation_state"] == "closed"
    assert report["blocking_issues"][0]["kind"] == "runtime_freeze_lockdown"
    assert "runtime_freeze_lockdown" in report["reason_codes"]

    validation = validate_governed_runtime_execution_session_report(report)
    assert validation["ok"] is True


def test_runtime_freeze_escalation_is_deterministic_for_same_payload() -> None:
    payload = {
        "runtime_frozen": True,
        "denied": True,
        "reason": "runtime locked",
        "freeze_id": "freeze-002",
    }

    first = escalate_runtime_freeze_to_governed_session(
        freeze_decision=payload,
        source_execution_id="execution-002",
    )
    second = escalate_runtime_freeze_to_governed_session(
        freeze_decision=payload,
        source_execution_id="execution-002",
    )

    assert first["execution_session_id"] == second["execution_session_id"]
    assert first["continuation_contract"]["continuation_id"] == second["continuation_contract"]["continuation_id"]


def test_non_frozen_state_keeps_continuation_available() -> None:
    report = build_governed_runtime_lockdown_session_report(
        freeze_state={
            "runtime_frozen": False,
            "reason": "",
        },
        source_execution_id="execution-open",
    )

    assert report["session_state"] == "running"
    assert report["continuation_contract"]["can_continue"] is True
    assert report["blocking_issues"] == []

    validation = validate_governed_runtime_execution_session_report(report)
    assert validation["ok"] is True

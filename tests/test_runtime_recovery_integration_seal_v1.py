from core.runtime.runtime_recovery_integration import (

    INTEGRATION_STATUS_BLOCKED,
    INTEGRATION_STATUS_READY_TO_CONTINUE,
    INTEGRATION_STATUS_REVIEW_REQUIRED,
    seal_runtime_recovery_integration,
)
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy, pytest.mark.integration]



def test_recovery_integration_ready_to_continue():
    seal = seal_runtime_recovery_integration(
        chain={
            "recovery_id": "recovery-1",
            "source_session_id": "session-1",
            "status": "verified",
            "source_failure": {"error": "tool_error"},
        },
        execution={"status": "completed"},
        continuation={"status": "ready_to_continue"},
    )

    payload = seal.to_dict()

    assert payload["sealed"] is True
    assert payload["recovery_id"] == "recovery-1"
    assert payload["source_session_id"] == "session-1"
    assert payload["final_status"] == INTEGRATION_STATUS_READY_TO_CONTINUE
    assert payload["next_action"] == "resume_runtime"
    assert len(payload["audit_events"]) == 3


def test_recovery_integration_blocks_unapproved_rollback():
    seal = seal_runtime_recovery_integration(
        chain={
            "recovery_id": "recovery-rollback",
            "source_session_id": "session-rollback",
            "status": "verified",
            "rollback_required": True,
        },
        execution={
            "status": "blocked",
            "rollback_required": True,
            "rollback_executed": False,
        },
        continuation={"status": "blocked"},
    )

    payload = seal.to_dict()

    assert payload["sealed"] is True
    assert payload["rollback_required"] is True
    assert payload["rollback_executed"] is False
    assert payload["approval_required"] is True
    assert payload["approved"] is False
    assert payload["final_status"] == INTEGRATION_STATUS_BLOCKED
    assert payload["next_action"] == "wait_for_recovery_approval"


def test_recovery_integration_allows_approved_high_risk_recovery():
    seal = seal_runtime_recovery_integration(
        chain={
            "recovery_id": "recovery-approved",
            "source_session_id": "session-approved",
            "rollback_required": True,
        },
        execution={
            "status": "completed",
            "rollback_required": True,
            "rollback_executed": False,
        },
        continuation={"status": "ready_to_continue"},
        approval_granted=True,
    )

    payload = seal.to_dict()

    assert payload["sealed"] is True
    assert payload["approval_required"] is True
    assert payload["approved"] is True
    assert payload["final_status"] == INTEGRATION_STATUS_READY_TO_CONTINUE


def test_recovery_integration_extended_mutation_requires_review():
    seal = seal_runtime_recovery_integration(
        chain={
            "recovery_id": "recovery-review",
            "source_session_id": "session-review",
            "status": "verified",
        },
        execution={"status": "completed"},
        continuation={"status": "ready_to_continue"},
        metadata={"mutation_scope": "extended"},
    )

    payload = seal.to_dict()

    assert payload["sealed"] is True
    assert payload["approval_required"] is True
    assert payload["final_status"] == INTEGRATION_STATUS_REVIEW_REQUIRED
    assert payload["next_action"] == "wait_for_recovery_review"


def test_recovery_integration_fingerprint_detects_mutation():
    seal = seal_runtime_recovery_integration(
        chain={"recovery_id": "recovery-fingerprint"},
        execution={"status": "completed"},
        continuation={"status": "ready_to_continue"},
    )

    payload = seal.to_dict()
    payload["final_status"] = "tampered"

    assert seal.verify() is True
    assert payload["sealed"] is True
    assert payload["final_status"] == "tampered"

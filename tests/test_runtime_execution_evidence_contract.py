from __future__ import annotations

from core.runtime.governed_runtime_execution_session import (

    build_governed_runtime_execution_session_report,
)
from core.runtime.runtime_execution_result import build_runtime_execution_result
from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



CANONICAL_EVIDENCE_FIELDS = {
    "execution_id",
    "execution_source",
    "execution_status",
    "execution_legality",
    "timestamp",
}


def test_legal_execution_evidence_is_canonical_and_propagated() -> None:
    payload = build_runtime_execution_result(
        {
            "ok": True,
            "execution_id": "exec-1",
            "timestamp": "2026-05-24T00:00:00Z",
            "status": "succeeded",
            "metadata": {
                "execution_source": "runtime_execution_gateway",
                "runtime_session_id": "session-1",
            },
        }
    )

    evidence = payload["execution_evidence"]

    assert CANONICAL_EVIDENCE_FIELDS <= set(evidence)
    assert evidence["execution_id"] == "exec-1"
    assert evidence["execution_source"] == "runtime_execution_gateway"
    assert evidence["execution_status"] == "succeeded"
    assert evidence["execution_legality"] == "legal"
    assert evidence["runtime_session_id"] == "session-1"
    assert payload["evidence"]["execution_evidence"] == evidence
    assert payload["metadata"]["execution_evidence"] == evidence


def test_denied_execution_evidence_preserves_denial_metadata() -> None:
    payload = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "blocked": True,
            "execution_id": "exec-denied",
            "timestamp": "2026-05-24T00:00:01Z",
            "status": "denied",
            "metadata": {
                "execution_source": "runtime_execution_gateway",
                "denial_reason": "policy_denied",
            },
        }
    )

    evidence = payload["execution_evidence"]

    assert payload["executed"] is False
    assert evidence["execution_legality"] == "denied"
    assert evidence["denial_reason"] == "policy_denied"
    assert payload["metadata"]["denial_reason"] == "policy_denied"


def test_failed_execution_evidence_preserves_failure_evidence() -> None:
    payload = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "failed": True,
            "execution_id": "exec-failed",
            "timestamp": "2026-05-24T00:00:02Z",
            "status": "failed",
            "error_type": "RuntimeError",
            "message": "boom",
            "metadata": {"execution_source": "step_executor"},
        }
    )

    evidence = payload["execution_evidence"]

    assert payload["executed"] is False
    assert evidence["execution_legality"] == "failed"
    assert evidence["failure_evidence"]["error_type"] == "RuntimeError"
    assert evidence["failure_evidence"]["message"] == "boom"


def test_duplicate_execution_evidence_is_preserved_for_audit() -> None:
    payload = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "execution_id": "exec-outer",
            "timestamp": "2026-05-24T00:00:03Z",
            "metadata": {"execution_source": "runtime_execution_result"},
            "runtime_execution_result": {
                "execution_id": "exec-inner",
                "execution_source": "runtime_execution_gateway",
                "execution_status": "succeeded",
                "execution_legality": "legal",
            },
        }
    )

    evidence = payload["execution_evidence"]

    assert payload["executed"] is False
    assert evidence["execution_legality"] == "duplicate"
    assert evidence["duplicate_execution_propagation"] is True
    assert evidence["duplicate_execution_evidence"]["execution_id"] == "exec-inner"


def test_runtime_session_exposes_execution_evidence() -> None:
    session = RuntimeExecutionSessionManager().create_session(
        "session-1",
        "life-1",
        source="runtime_execution_session",
    )

    assert session.execution_evidence["runtime_session_id"] == "session-1"
    assert session.execution_evidence["execution_id"] == "life-1"
    assert session.execution_evidence["execution_source"] == "runtime_execution_session"


def test_governed_execution_report_exposes_execution_evidence() -> None:
    report = build_governed_runtime_execution_session_report(
        action_execution_report={
            "governed_action_execution_id": "governed-exec-1",
            "execution_state": "blocked",
            "denial_reason": "review_required",
        }
    )

    evidence = report["execution_evidence"]

    assert evidence["execution_id"] == "governed-exec-1"
    assert evidence["execution_source"] == "governed_runtime_execution_session"
    assert evidence["execution_legality"] == "denied"
    assert evidence["denial_reason"] == "review_required"
    assert evidence["runtime_session_id"] == report["execution_session_id"]

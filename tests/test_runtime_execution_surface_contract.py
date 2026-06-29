from __future__ import annotations

from core.runtime.runtime_execution_result import build_runtime_execution_result
import pytest

pytestmark = [pytest.mark.contract]




def test_legal_execution_can_set_executed_true() -> None:
    payload = build_runtime_execution_result(
        {
            "ok": True,
            "metadata": {"execution_source": "runtime_execution_gateway"},
            "status": "succeeded",
        }
    )

    assert payload["executed"] is True
    assert payload["failed"] is False
    assert payload["blocked"] is False
    assert payload["execution_source"] == "runtime_execution_gateway"
    assert payload["execution_status"] == "succeeded"
    assert payload["execution_legality"] == "legal"
    assert payload["metadata"]["execution_legality"] == "legal"


def test_denied_execution_cannot_set_executed_true() -> None:
    payload = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "blocked": True,
            "status": "denied",
            "metadata": {
                "execution_source": "runtime_execution_gateway",
                "denial_reason": "permission_denied",
            },
        }
    )

    assert payload["executed"] is False
    assert payload["ok"] is False
    assert payload["blocked"] is True
    assert payload["failed"] is False
    assert payload["execution_legality"] == "denied"
    assert payload["denial_reason"] == "permission_denied"


def test_failed_execution_cannot_be_marked_executed_true() -> None:
    payload = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "failed": True,
            "status": "failed",
            "metadata": {"execution_source": "step_executor"},
        }
    )

    assert payload["executed"] is False
    assert payload["ok"] is False
    assert payload["failed"] is True
    assert payload["execution_legality"] == "failed"
    assert payload["denial_reason"] == "execution_failed"


def test_duplicate_execution_propagation_is_rejected_and_identified() -> None:
    payload = build_runtime_execution_result(
        {
            "ok": True,
            "executed": True,
            "metadata": {"execution_source": "runtime_execution_result"},
            "runtime_execution_result": {
                "executed": True,
                "execution_source": "runtime_execution_gateway",
            },
        }
    )

    assert payload["executed"] is False
    assert payload["ok"] is False
    assert payload["execution_legality"] == "duplicate"
    assert payload["duplicate_execution_propagation"] is True
    assert payload["denial_reason"] == "duplicate_execution_propagation"

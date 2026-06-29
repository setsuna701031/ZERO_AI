from __future__ import annotations

from core.runtime.runtime_lifecycle_context import (

    propagate_lifecycle_status,
    validate_lifecycle_status_propagation,
)
import pytest

pytestmark = [pytest.mark.contract]



def test_lifecycle_propagation_allows_queued_running_finished_flow() -> None:
    running = propagate_lifecycle_status("queued", "running")
    finished = propagate_lifecycle_status(running["status"], "finished")

    assert running["allowed"] is True
    assert running["transitioned"] is True
    assert running["status"] == "running"
    assert running["canonical_status"] == "running"

    assert finished["allowed"] is True
    assert finished["transitioned"] is True
    assert finished["status"] == "finished"
    assert finished["canonical_status"] == "executed"


def test_lifecycle_propagation_allows_queued_running_failed_flow() -> None:
    running = propagate_lifecycle_status("queued", "running")
    failed = propagate_lifecycle_status(running["status"], "failed")

    assert failed["allowed"] is True
    assert failed["transitioned"] is True
    assert failed["status"] == "failed"
    assert failed["canonical_status"] == "failed"


def test_lifecycle_propagation_does_not_overwrite_blocked() -> None:
    result = propagate_lifecycle_status("blocked", "running")

    assert result["allowed"] is False
    assert result["transitioned"] is False
    assert result["status"] == "blocked"
    assert result["canonical_status"] == "blocked"
    assert result["reason"] == "blocked_status_is_not_overwritten_by_lifecycle_propagation"


def test_lifecycle_propagation_rejects_illegal_transition_and_keeps_original() -> None:
    result = propagate_lifecycle_status("queued", "finished")

    assert result["allowed"] is False
    assert result["transitioned"] is False
    assert result["status"] == "queued"
    assert result["canonical_status"] == "queued"
    assert result["reason"] == "illegal_lifecycle_propagation_transition:queued->executed"


def test_lifecycle_propagation_validation_reports_canonical_aliases() -> None:
    validation = validate_lifecycle_status_propagation("running", "finished")

    assert validation == {
        "from_status": "running",
        "to_status": "executed",
        "allowed": True,
        "reason": "lifecycle_propagation_transition_allowed",
    }

from __future__ import annotations

from core.runtime.runtime_burnin_runner import run_prediction_burnin, run_simulation_burnin
from core.runtime.runtime_constitution_freeze import (

    RuntimeInvariant,
    assert_prediction_invariant,
    assert_simulation_invariant,
    create_constitution_snapshot,
)
from core.runtime.runtime_prediction_engine import predict_mutation_impact
from core.runtime.runtime_simulation_engine import simulate_runtime_step
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def test_constitution_rejects_prediction_as_authority() -> None:
    try:
        assert_prediction_invariant({"prediction_id": "p", "authoritative": True})
    except AssertionError as exc:
        assert "authority" in str(exc)
    else:
        raise AssertionError("prediction-as-authority should fail")


def test_constitution_rejects_simulation_mutation() -> None:
    try:
        assert_simulation_invariant({"branch_id": "b", "mutation_allowed": True})
    except AssertionError as exc:
        assert "mutate" in str(exc)
    else:
        raise AssertionError("simulation mutation should fail")


def test_constitution_rejects_simulation_commit() -> None:
    try:
        assert_simulation_invariant({"branch_id": "b", "committed": True})
    except AssertionError as exc:
        assert "commit" in str(exc)
    else:
        raise AssertionError("simulation commit should fail")


def test_constitution_rejects_approval_bypass_by_prediction() -> None:
    try:
        assert_prediction_invariant({"prediction_id": "p", "approval_state": "approved"})
    except AssertionError as exc:
        assert "approval" in str(exc)
    else:
        raise AssertionError("prediction approval bypass should fail")


def test_burn_in_detects_prediction_authority_drift() -> None:
    result = run_prediction_burnin(iterations=2, inject_authority_drift=True)

    assert result["ok"] is False
    assert result["authority_drift"] is True


def test_burn_in_detects_simulation_mutation_drift() -> None:
    result = run_simulation_burnin(iterations=2, inject_mutation_drift=True)

    assert result["ok"] is False
    assert result["mutation_drift"] is True


def test_prediction_invariant_snapshot_deterministic() -> None:
    assert_prediction_invariant(predict_mutation_impact(_context()))
    first = create_constitution_snapshot(violations=())
    second = create_constitution_snapshot(violations=())

    assert first.normalized_digest == second.normalized_digest
    assert RuntimeInvariant.PREDICTION_CANNOT_GRANT_AUTHORITY in {item.invariant for item in first.invariant_snapshots}


def test_simulation_invariant_snapshot_deterministic() -> None:
    assert_simulation_invariant(simulate_runtime_step(_context()))
    first = create_constitution_snapshot(violations=())
    second = create_constitution_snapshot(violations=())

    assert first.normalized_digest == second.normalized_digest
    assert RuntimeInvariant.SIMULATION_CANNOT_MUTATE in {item.invariant for item in first.invariant_snapshots}


def _context():
    return {
        "task_id": "task-constitution-prediction",
        "step_id": "step-constitution-prediction",
        "trace_id": "trace-constitution-prediction",
        "source_transaction_id": "runtime_tx:constitution-prediction",
        "affected_files": ["workspace/shared/constitution-prediction.txt"],
    }

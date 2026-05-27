from __future__ import annotations

from core.runtime.runtime_prediction_engine import (
    RuntimePredictionRisk,
    assert_prediction_non_authoritative,
    normalize_prediction_result,
    predict_mutation_impact,
    predict_repair_outcome,
    predict_replay_divergence,
    predict_rollback_risk,
    predict_stabilization_probability,
)
from core.runtime.runtime_transaction_registry import list_transactions


def test_mutation_impact_prediction_creates_stable_result() -> None:
    first = predict_mutation_impact(_context())
    second = predict_mutation_impact(_context())

    assert first.prediction_id == second.prediction_id
    assert normalize_prediction_result(first) == normalize_prediction_result(second)


def test_repair_outcome_prediction_uses_memory_refs() -> None:
    result = predict_repair_outcome(_context(repair_strategy="strategy-prediction"))

    assert result.memory_refs
    assert result.predicted_outcome


def test_rollback_risk_prediction_stable() -> None:
    first = predict_rollback_risk(_context())
    second = predict_rollback_risk(_context())

    assert first.normalized_digest == second.normalized_digest
    assert first.rollback_risk in RuntimePredictionRisk


def test_replay_divergence_prediction_stable() -> None:
    first = predict_replay_divergence(_context())
    second = predict_replay_divergence(_context())

    assert first.prediction_id == second.prediction_id
    assert first.replay_divergence_risk in RuntimePredictionRisk


def test_stabilization_probability_bounded_0_1() -> None:
    result = predict_stabilization_probability(_context())

    assert 0.0 <= result.stabilization_probability <= 1.0


def test_prediction_is_non_authoritative() -> None:
    assert assert_prediction_non_authoritative(predict_mutation_impact(_context())) is True


def test_prediction_cannot_create_transaction() -> None:
    before = tuple(tx.transaction_id for tx in list_transactions())
    result = predict_mutation_impact(_context())
    after = tuple(tx.transaction_id for tx in list_transactions())

    assert result.authoritative is False
    assert before == after


def test_prediction_cannot_grant_approval() -> None:
    try:
        assert_prediction_non_authoritative({"prediction_id": "p", "approval_state": "approved"})
    except AssertionError as exc:
        assert "approval" in str(exc)
    else:
        raise AssertionError("prediction approval bypass should fail")


def test_prediction_preserves_lineage() -> None:
    result = predict_mutation_impact(_context())

    assert result.source_transaction_id == "runtime_tx:prediction-source"
    assert "prediction.source_lineage_immutable" in result.invariant_refs


def test_prediction_digest_stable() -> None:
    result = predict_mutation_impact(_context())

    assert result.normalized_digest
    assert result.prediction_id.endswith(result.normalized_digest[:16])


def _context(**overrides):
    from core.runtime.runtime_memory_engine import RuntimeMemoryKind, append_runtime_memory, create_memory_record

    record = append_runtime_memory(
        create_memory_record(
            kind=RuntimeMemoryKind.REPAIR_HISTORY,
            task_id="task-prediction",
            step_id="step-prediction",
            trace_id="trace-prediction",
            transaction_id="runtime_tx:prediction-source",
            replay_run_id="replay_run:prediction",
            recovery_attempt_id="runtime_recovery:prediction",
            repair_loop_id="repair_loop:prediction",
            evidence_refs=["runtime_evidence:prediction"],
            failure_signature="failure-prediction",
            repair_strategy="strategy-prediction",
            stabilization_result="stabilized",
            terminal_state="stabilized",
            semantic_tags=["repair", "stabilization"],
        )
    )
    payload = {
        "task_id": "task-prediction",
        "step_id": "step-prediction",
        "trace_id": "trace-prediction",
        "source_transaction_id": "runtime_tx:prediction-source",
        "source_replay_run_id": "replay_run:prediction",
        "source_recovery_attempt_id": "runtime_recovery:prediction",
        "source_repair_loop_id": "repair_loop:prediction",
        "failure_signature": "failure-prediction",
        "repair_strategy": "strategy-prediction",
        "affected_files": ["workspace/shared/prediction.txt"],
        "source_memory_ids": [record.memory_id],
    }
    payload.update(overrides)
    return payload

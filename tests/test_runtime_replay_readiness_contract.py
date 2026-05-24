from __future__ import annotations

from core.runtime.runtime_execution_result import build_runtime_execution_result
from core.runtime.runtime_replay_readiness import (
    CANONICAL_REPLAY_READINESS_FIELDS,
    build_runtime_replay_readiness_fields,
)
from core.runtime.runtime_transaction_context import build_transaction_boundary_metadata


def _legal_payload() -> dict:
    recovery = {
        "recovery_readiness": "ready",
        "replay_readiness": "ready",
        "deterministic_state": True,
        "resumable_state": True,
        "recovery_block_reason": "recovery_ready",
    }
    return {
        "execution_evidence": {
            "execution_id": "exec-replay",
            "execution_source": "runtime_execution_gateway",
            "execution_status": "succeeded",
            "execution_legality": "legal",
        },
        "transaction_boundary": {
            "transaction_id": "tx-replay",
            "transaction_status": "committed",
            "transaction_legality": "legal",
        },
        "authority_seal": {
            "authority_source": "runtime_execution_gateway",
            "authority_scope": "execution_gateway",
            "authority_status": "allowed",
            "ownership_source": "core.runtime.executor",
        },
        "consistency_seal": {
            "consistency_status": "consistent",
            "runtime_state_snapshot": {"execution_status": "succeeded"},
        },
        "runtime_closure": {
            "closure_status": "finalized",
            "immutable_state": True,
            "closure_evidence": {"mismatch_evidence": []},
        },
        "recovery_readiness_seal": recovery,
        **recovery,
    }


def test_legal_deterministic_replay_readiness() -> None:
    readiness = build_runtime_replay_readiness_fields(
        _legal_payload(),
        artifact_type="execution",
        artifact_id="exec-replay",
    )

    assert set(CANONICAL_REPLAY_READINESS_FIELDS) <= set(readiness)
    assert readiness["replay_admissible"] is True
    assert readiness["deterministic_replay"] is True
    assert readiness["replay_block_reason"] == "replay_admissible"
    assert readiness["replay_snapshot"]["replay_snapshot_ready"] is True
    assert readiness["replay_state_hash"]


def test_nondeterministic_state_rejects_replay_admissible() -> None:
    payload = _legal_payload()
    payload["deterministic_state"] = False
    payload["recovery_readiness_seal"]["deterministic_state"] = False

    readiness = build_runtime_replay_readiness_fields(payload)

    assert readiness["replay_admissible"] is False
    assert readiness["deterministic_replay"] is False
    assert "nondeterministic_state" in readiness["replay_block_reason"]
    assert readiness["replay_evidence"]["deterministic_mismatch_evidence"][0]["kind"] == "nondeterministic_state"


def test_missing_evidence_replay_rejection() -> None:
    readiness = build_runtime_replay_readiness_fields(
        {
            "recovery_readiness_seal": {
                "deterministic_state": True,
                "recovery_readiness": "ready",
            }
        }
    )

    assert readiness["deterministic_replay"] is False
    assert readiness["replay_admissible"] is False
    assert "missing_replay_evidence" in readiness["replay_block_reason"]


def test_finalized_mismatch_rejects_replay_safe() -> None:
    payload = _legal_payload()
    payload["runtime_closure"] = {
        "closure_status": "finalized",
        "immutable_state": True,
        "closure_evidence": {"mismatch_evidence": [{"kind": "overwrite_attempt"}]},
    }

    readiness = build_runtime_replay_readiness_fields(payload)

    assert readiness["replay_admissible"] is False
    assert readiness["replay_evidence"]["replay_safe"] is False
    assert "finalized_immutable_mismatch" in readiness["replay_block_reason"]


def test_incomplete_transaction_rejects_replay_snapshot_ready() -> None:
    boundary = build_transaction_boundary_metadata(
        {
            "transaction_status": "committed",
            "transaction_source": "unit",
            "transaction_scope": "readiness",
        }
    )
    readiness = build_runtime_replay_readiness_fields(
        {
            **_legal_payload(),
            "transaction_boundary": boundary,
        }
    )

    assert boundary["transaction_legality"] == "incomplete"
    assert readiness["replay_admissible"] is False
    assert readiness["replay_snapshot"]["replay_snapshot_ready"] is False
    assert "incomplete_transaction" in readiness["replay_block_reason"]


def test_runtime_execution_result_propagates_replay_readiness_fields() -> None:
    result = build_runtime_execution_result(
        {
            "ok": True,
            "status": "succeeded",
            "execution_id": "exec-replay-propagation",
            "transaction_boundary": _legal_payload()["transaction_boundary"],
            "authority_source": "runtime_execution_gateway",
            "authority_scope": "execution_gateway",
            "ownership_source": "core.runtime.executor",
            "consistency_seal": _legal_payload()["consistency_seal"],
            "runtime_closure": _legal_payload()["runtime_closure"],
        }
    )

    assert set(CANONICAL_REPLAY_READINESS_FIELDS) <= set(result)
    assert "replay_evidence" in result["evidence"]
    assert "replay_readiness_seal" in result["metadata"]

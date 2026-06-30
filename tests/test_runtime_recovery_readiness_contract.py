from __future__ import annotations

from core.runtime.runtime_execution_result import build_runtime_execution_result
from core.runtime.runtime_recovery_readiness import (

    CANONICAL_RECOVERY_READINESS_FIELDS,
    build_runtime_recovery_readiness_fields,
)
from core.runtime.runtime_transaction_context import build_transaction_boundary_metadata
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def _legal_payload() -> dict:
    return {
        "execution_evidence": {
            "execution_id": "exec-ready",
            "execution_source": "runtime_execution_gateway",
            "execution_status": "succeeded",
            "execution_legality": "legal",
        },
        "transaction_boundary": {
            "transaction_id": "tx-ready",
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
    }


def test_legal_recovery_readiness() -> None:
    readiness = build_runtime_recovery_readiness_fields(
        _legal_payload(),
        artifact_type="execution",
        artifact_id="exec-ready",
    )

    assert set(CANONICAL_RECOVERY_READINESS_FIELDS) <= set(readiness)
    assert readiness["recovery_readiness"] == "ready"
    assert readiness["replay_readiness"] == "ready"
    assert readiness["deterministic_state"] is True
    assert readiness["resumable_state"] is True
    assert readiness["recovery_block_reason"] == "recovery_ready"


def test_inconsistent_runtime_rejects_recovery_ready() -> None:
    payload = _legal_payload()
    payload["consistency_seal"] = {
        "consistency_status": "mismatch",
        "mismatch_evidence": [{"kind": "lifecycle_execution_mismatch"}],
    }

    readiness = build_runtime_recovery_readiness_fields(payload)

    assert readiness["recovery_readiness"] == "blocked"
    assert "inconsistent_runtime_state" in readiness["recovery_block_reason"]
    assert readiness["recovery_evidence"]["recovery_block_evidence"][0]["kind"] == "inconsistent_runtime_state"


def test_missing_evidence_rejects_recovery_ready() -> None:
    readiness = build_runtime_recovery_readiness_fields(
        {
            "authority_seal": {
                "authority_status": "allowed",
                "ownership_source": "core.runtime.executor",
            }
        }
    )

    assert readiness["recovery_readiness"] == "blocked"
    assert "missing_recovery_evidence" in readiness["recovery_block_reason"]
    assert readiness["recovery_evidence"]["recovery_block_evidence"][0]["missing_evidence"]


def test_finalized_mismatch_rejects_replay_ready() -> None:
    payload = _legal_payload()
    payload["runtime_closure"] = {
        "closure_status": "finalized",
        "immutable_state": True,
        "closure_evidence": {
            "mismatch_evidence": [{"kind": "overwrite_attempt"}],
        },
    }

    readiness = build_runtime_recovery_readiness_fields(payload)

    assert readiness["replay_readiness"] == "blocked"
    assert readiness["recovery_readiness"] == "blocked"
    assert "finalized_immutable_mismatch" in readiness["recovery_block_reason"]


def test_incomplete_transaction_rejects_deterministic_state() -> None:
    boundary = build_transaction_boundary_metadata(
        {
            "transaction_status": "committed",
            "transaction_source": "unit",
            "transaction_scope": "readiness",
        }
    )
    readiness = build_runtime_recovery_readiness_fields(
        {
            **_legal_payload(),
            "transaction_boundary": boundary,
        }
    )

    assert boundary["transaction_legality"] == "incomplete"
    assert readiness["deterministic_state"] is False
    assert readiness["replay_readiness"] == "blocked"
    assert "incomplete_transaction" in readiness["recovery_block_reason"]


def test_runtime_execution_result_propagates_recovery_readiness_fields() -> None:
    result = build_runtime_execution_result(
        {
            "ok": True,
            "status": "succeeded",
            "execution_id": "exec-propagation",
            "transaction_boundary": _legal_payload()["transaction_boundary"],
            "authority_source": "runtime_execution_gateway",
            "authority_scope": "execution_gateway",
            "ownership_source": "core.runtime.executor",
            "consistency_seal": _legal_payload()["consistency_seal"],
            "runtime_closure": _legal_payload()["runtime_closure"],
        }
    )

    assert set(CANONICAL_RECOVERY_READINESS_FIELDS) <= set(result)
    assert "recovery_evidence" in result["evidence"]
    assert "recovery_readiness_seal" in result["metadata"]

from __future__ import annotations

from core.evidence.evidence_chain import EvidenceChain
from core.evidence.evidence_record import EvidenceRecord
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def _record(evidence_id: str, state: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        goal_id="goal_a",
        subgoal_id="subgoal_a",
        source="runtime_result",
        summary={"state": state},
        timestamp="2026-01-01T00:00:00+00:00",
        validation_state=state,
    )


def test_chain_is_read_only_summary() -> None:
    chain = EvidenceChain.from_records(
        "goal_a",
        [
            _record("evidence_validated", "validated"),
            _record("evidence_rejected", "rejected"),
            _record("evidence_pending", "pending"),
        ],
    )

    assert chain.validated_count == 0
    assert chain.rejected_count == 1
    assert chain.pending_count == 1
    assert chain.has_validated_evidence is False
    assert chain.validated_evidence_ids == []


def test_chain_has_no_write_or_completion_authority() -> None:
    chain = EvidenceChain.from_records("goal_a", [_record("evidence_validated", "validated")])

    assert not hasattr(chain, "add_record")
    assert not hasattr(chain, "validate")
    assert not hasattr(chain, "register_evidence")
    assert not hasattr(chain, "complete_goal")
    assert not hasattr(chain, "update_goal")

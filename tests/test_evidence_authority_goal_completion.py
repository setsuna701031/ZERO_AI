from __future__ import annotations

from pathlib import Path

from core.evidence.decision_evidence import DecisionEvidenceRepository, build_decision_evidence
from core.evidence.evidence_authority import EvidenceAuthority
from core.evidence.evidence_collector import EvidenceCollector
from core.evidence.evidence_contract import EvidenceContract
from core.evidence.evidence_repository import EvidenceRepository
from core.evidence.evidence_validator import EvidenceValidator
import pytest

pytestmark = [pytest.mark.contract]




def _contract() -> EvidenceContract:
    return EvidenceContract(
        plan_id="plan_a",
        goal_id="goal_a",
        subgoal_id="subgoal_a",
        reason="evidence_required_for_goal_completion",
    )


def test_goal_completion_requires_validated_evidence_summary(tmp_path: Path) -> None:
    repository = EvidenceRepository(tmp_path)
    authority = EvidenceAuthority(tmp_path, evidence_repository=repository)
    contract = _contract()

    pending = EvidenceCollector().collect(
        contract,
        source="runtime_result",
        summary={"ok": True},
        timestamp="2026-01-01T00:00:00+00:00",
    )
    repository.add_record(pending)
    pending_chain = authority.get_goal_chain("goal_a")

    assert pending_chain.has_validated_evidence is False
    assert pending_chain.validated_count == 0
    assert pending_chain.pending_count == 1

    validated = EvidenceValidator().validate(pending)
    repository.add_record(validated)
    validated_chain = authority.get_goal_chain("goal_a")

    assert validated_chain.has_validated_evidence is True
    assert validated_chain.validated_count == 1
    assert validated.evidence_id in validated_chain.validated_evidence_ids



def test_goal_completion_cannot_be_declared_by_evidence_components(tmp_path: Path) -> None:
    repository = EvidenceRepository(tmp_path)
    authority = EvidenceAuthority(tmp_path, evidence_repository=repository)
    collector = EvidenceCollector()
    validator = EvidenceValidator()
    chain = authority.get_goal_chain("goal_a")

    assert not hasattr(collector, "complete_goal")
    assert not hasattr(validator, "complete_goal")
    assert not hasattr(repository, "complete_goal")
    assert not hasattr(chain, "complete_goal")
    assert not hasattr(authority, "complete_goal")



def test_decision_evidence_repository_routes_through_evidence_authority(tmp_path: Path) -> None:
    evidence_repository = EvidenceRepository(tmp_path)
    evidence_authority = EvidenceAuthority(tmp_path, evidence_repository=evidence_repository)
    decision_repository = DecisionEvidenceRepository(
        tmp_path,
        evidence_repository=evidence_repository,
        evidence_authority=evidence_authority,
    )
    decision = build_decision_evidence(
        cycle={
            "goal_id": "goal_a",
            "cycle_index": 0,
            "adaptive_decision_record": {
                "decision": "complete",
                "outcome_class": "completed",
                "reason": "validated evidence exists",
            },
            "adaptive_planning_record": {
                "outcome_class": "completed",
                "next_action": "stop",
                "decision_reason": "validated evidence exists",
            },
            "runner_result": {"runtime_result": {"state": "completed", "iterations": []}},
        },
        continuation_work_item={},
        replan_record={},
    )

    saved = decision_repository.save(decision)
    chain = evidence_authority.get_decision_chain("goal_a")

    assert saved["evidence_authority_schema"] == "zero.evidence_authority.v1"
    assert saved["evidence_source"] == "decision_evidence"
    assert saved["evidence_id"] in chain.evidence_ids
    assert chain.has_validated_evidence is False
    assert chain.pending_count == 1
    assert not hasattr(decision_repository, "complete_goal")

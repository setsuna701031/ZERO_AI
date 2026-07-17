from __future__ import annotations

import pytest

import core.evidence.evidence_validator as evidence_validator_module
import core.goals.goal_completion_authority as completion_authority_module
from core.evidence import EvidenceChain, EvidenceRecord, EvidenceRepository, EvidenceValidator
from core.goals import GoalRepository, PersistentGoal
from core.goals.goal_completion_authority import (

    GoalCompletionAuthority,
    GoalCompletionResult,
    is_accepted_goal_completion_result,
)
from core.program.engineering_program_state_machine import EngineeringProgramStateMachine
from core.session.engineering_session_state_machine import EngineeringSessionStateMachine
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_lifecycle_state_machine import EngineeringLifecycleStateMachine
pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def _attestation(goal_id: str, *, goal_lineage=None):
    evidence = EvidenceValidator().validate(EvidenceRecord(
        "e1", goal_id, None, "test", "ok", "now",
        metadata={**goal_lineage, "goal_lineage": goal_lineage} if goal_lineage else {},
    ))
    return GoalCompletionAuthority().complete_goal(
        goal_id=goal_id,
        evidence_refs=[evidence],
        all_subgoals_completed=True,
        goal_lineage=goal_lineage,
    )


def test_mutable_provenance_registry_injection_cannot_forge_authority(monkeypatch) -> None:
    evidence = EvidenceRecord("fake", "goal-1", None, "fake", "fake", "now", validation_state="validated")
    monkeypatch.setattr(evidence_validator_module, "_VALIDATED_EVIDENCE", {id(evidence): evidence}, raising=False)
    assert evidence_validator_module.is_provenance_validated_evidence(evidence) is False

    forged = GoalCompletionResult(True, "goal-1", "active", "completed", "fake", evidence_refs=[evidence])
    monkeypatch.setattr(
        completion_authority_module,
        "_ISSUED_COMPLETION_ATTESTATIONS",
        {id(forged): forged},
        raising=False,
    )
    assert is_accepted_goal_completion_result(forged) is False


def test_validated_evidence_for_another_goal_cannot_complete_target_goal() -> None:
    evidence = EvidenceValidator().validate(EvidenceRecord("e1", "goal-a", None, "test", "ok", "now"))
    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal-b",
        evidence_refs=[evidence],
        all_subgoals_completed=True,
    )
    assert result.accepted is False
    assert result.blocked_reason == "completed_goal_requires_validated_evidence"


def test_attestation_for_another_goal_cannot_complete_repository_goal(tmp_path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-b", "B", status="active"))
    with pytest.raises(ValueError, match="canonical_completion_attestation_required"):
        repository.update_goal_status("goal-b", "completed", completion_attestation=_attestation("goal-a"))


def test_attestation_for_another_goal_cannot_complete_lifecycle_or_session() -> None:
    attestation = _attestation("goal-a")
    lifecycle = EngineeringLifecycleStateMachine().evaluate_adaptive_loop(
        {"goal_id": "goal-b", "adaptive_replan_state": {"loop_action": "complete"}},
        from_state="running",
        completion_attestation=attestation,
    )
    session = EngineeringSessionStateMachine().evaluate_lifecycle(
        {"lifecycle_state": "completed", "task_id": "goal-b"},
        from_state="active",
        completion_attestation=attestation,
    )
    assert lifecycle.accepted is False
    assert session.accepted is False


def test_engineering_goal_repository_rejects_direct_completed_status(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    with pytest.raises(ValueError, match="canonical_completion_attestation_required"):
        repository.save_goal({"goal_id": "seeded-complete", "summary": "Goal", "status": "complete"})
    goal = repository.save_goal({"goal_id": "goal-1", "summary": "Goal"})
    with pytest.raises(ValueError, match="canonical_completion_attestation_required"):
        repository.update_goal("goal-1", {"status": "completed"})
    with pytest.raises(ValueError, match="canonical_completion_attestation_required"):
        repository.update_goal("goal-1", {"status": "complete"})
    completed = repository.update_goal(
        "goal-1",
        {"status": "completed"},
        completion_attestation=_attestation("goal-1", goal_lineage=goal["goal_lineage"]),
    )
    assert completed["status"] == "completed"


def test_program_completion_requires_subject_bound_canonical_attestation() -> None:
    machine = EngineeringProgramStateMachine()
    rejected = machine.evaluate_session(
        {"session_state": "completed", "accepted": True},
        from_state="active",
        goal_id="goal-1",
    )
    wrong = machine.evaluate_session(
        {"session_state": "completed", "accepted": True},
        from_state="active",
        goal_id="goal-1",
        completion_attestation=_attestation("goal-2"),
    )
    accepted = machine.evaluate_session(
        {"session_state": "completed", "accepted": True},
        from_state="active",
        goal_id="goal-1",
        completion_attestation=_attestation("goal-1"),
    )
    assert rejected.accepted is False
    assert wrong.accepted is False
    assert accepted.accepted is True


def test_serialized_validated_state_and_summary_are_descriptive_only() -> None:
    record = EvidenceRecord.from_mapping(
        {
            "evidence_id": "e1",
            "goal_id": "goal-1",
            "source": "transport",
            "summary": "ok",
            "timestamp": "now",
            "validation_state": "validated",
        }
    )
    chain = EvidenceChain.from_records("goal-1", [record])
    summary_chain = EvidenceChain.from_summary(
        {"goal_id": "goal-1", "validated_count": 1, "validated_evidence_ids": ["e1"]}
    )
    assert evidence_validator_module.is_provenance_validated_evidence(record) is False
    assert chain.has_validated_evidence is False
    assert chain.validated_evidence_refs == []
    assert summary_chain.has_validated_evidence is False


def test_persisted_validated_repository_output_is_descriptive_only_after_reload(tmp_path) -> None:
    repository = EvidenceRepository(tmp_path)
    evidence = EvidenceValidator().validate(EvidenceRecord("e1", "goal-1", None, "test", "ok", "now"))
    repository.add_record(evidence)
    assert repository.list_validated_by_goal("goal-1") == [evidence]

    reloaded = EvidenceRepository(tmp_path)
    assert reloaded.list_validated_by_goal("goal-1") == []
    assert reloaded.build_chain("goal-1").has_validated_evidence is False

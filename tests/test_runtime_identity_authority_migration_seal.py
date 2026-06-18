from __future__ import annotations

from core.evidence import EvidenceRecord, EvidenceValidator
from core.evidence.evidence_authority import EvidenceAuthority
from core.evidence.evidence_repository import EvidenceRepository
from core.goals.goal_completion_authority import GoalCompletionAuthority
from core.goals.goal_lineage_contract import extract_goal_lineage


def _lineage(root: str, *, session: str, runtime: str) -> dict[str, str]:
    return extract_goal_lineage(
        {
            "root_goal_id": root,
            "source_goal_id": root,
            "goal_id": root,
            "branch_type": "root",
            "branch_id": root,
            "session_id": session,
            "runtime_session_id": runtime,
        },
        require_complete=True,
    )


def _validated(root: str, *, session: str, runtime: str, evidence_id: str) -> EvidenceRecord:
    lineage = _lineage(root, session=session, runtime=runtime)
    return EvidenceValidator().validate(
        EvidenceRecord(
            evidence_id=evidence_id,
            goal_id=root,
            subgoal_id=None,
            source="runtime",
            summary="ok",
            timestamp="2026-06-18T00:00:00+00:00",
            metadata={**lineage, "goal_lineage": lineage},
        )
    )


def test_evidence_repository_keys_include_runtime_session_id(tmp_path) -> None:
    repository = EvidenceRepository(tmp_path, storage_path=tmp_path / "evidence.jsonl")
    evidence_a = repository.add_record(_validated("goal-a", session="session-a", runtime="runtime-a", evidence_id="same-evidence"))
    evidence_b = repository.add_record(_validated("goal-a", session="session-a", runtime="runtime-b", evidence_id="same-evidence"))

    records = repository.list_by_goal("goal-a", session_id="session-a")

    assert len(records) == 2
    assert repository._record_key(evidence_a) != repository._record_key(evidence_b)
    assert "runtime-a" in repository._record_key(evidence_a)
    assert "runtime-b" in repository._record_key(evidence_b)
    assert {item.metadata["runtime_session_id"] for item in records} == {"runtime-a", "runtime-b"}
    assert repository.get_record(
        "same-evidence",
        session_id="session-a",
        goal_lineage_id=evidence_a.metadata["goal_lineage_id"],
        root_goal_id="goal-a",
    ) == evidence_a
    assert repository.get_record(
        "same-evidence",
        session_id="session-a",
        goal_lineage_id=evidence_b.metadata["goal_lineage_id"],
        root_goal_id="goal-a",
    ) == evidence_b


def test_decision_evidence_does_not_derive_runtime_session_from_session(tmp_path) -> None:
    authority = EvidenceAuthority(tmp_path, evidence_repository=EvidenceRepository(tmp_path, storage_path=tmp_path / "evidence.jsonl"))

    projected = authority.register_decision_evidence(
        {
            "decision_id": "decision-a",
            "goal_id": "goal-a",
            "task_id": "task-a",
            "decision": "continue",
            "outcome_class": "recoverable",
            "decision_reason": "needs_more_work",
            "session_id": "session-a",
        }
    )
    stored = authority.list_records()[0]

    assert projected["evidence_id"] == "decision-a"
    assert stored.metadata["session_id"] == "session-a"
    assert stored.metadata["runtime_session_id"] == ""


def test_goal_completion_rejects_same_session_wrong_runtime_session(tmp_path) -> None:
    lineage = _lineage("goal-a", session="session-a", runtime="runtime-a")
    wrong_runtime = _validated("goal-a", session="session-a", runtime="runtime-b", evidence_id="evidence-b")

    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[wrong_runtime],
        all_subgoals_completed=True,
        goal_lineage=lineage,
    )

    assert result.completed is False
    assert result.reason == "goal_completion_evidence_runtime_session_mismatch"


def test_goal_completion_rejects_same_session_missing_runtime_session() -> None:
    lineage = _lineage("goal-a", session="session-a", runtime="runtime-a")
    metadata = {
        key: value
        for key, value in lineage.items()
        if key != "runtime_session_id"
    }
    missing_runtime = EvidenceValidator().validate(
        EvidenceRecord(
            evidence_id="evidence-missing-runtime",
            goal_id="goal-a",
            subgoal_id=None,
            source="runtime",
            summary="missing strict runtime identity",
            timestamp="2026-06-18T00:00:00+00:00",
            metadata={**metadata, "goal_lineage": metadata},
        )
    )

    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[missing_runtime],
        all_subgoals_completed=True,
        goal_lineage=lineage,
    )

    assert result.completed is False
    assert result.reason == "goal_completion_evidence_runtime_session_mismatch"


def test_goal_completion_accepts_matching_runtime_session(tmp_path) -> None:
    lineage = _lineage("goal-a", session="session-a", runtime="runtime-a")
    evidence = _validated("goal-a", session="session-a", runtime="runtime-a", evidence_id="evidence-a")

    result = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[evidence],
        all_subgoals_completed=True,
        goal_lineage=lineage,
    )

    assert result.completed is True
    assert result.session_id == "session-a"
    assert result.runtime_session_id == "runtime-a"

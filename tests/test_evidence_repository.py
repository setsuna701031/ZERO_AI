from pathlib import Path

from core.evidence import EvidenceRecord, EvidenceRepository, EvidenceValidator
from core.goals import GoalRepository, PersistentGoal


def _record(evidence_id: str, *, subgoal_id: str | None = "sub-1") -> EvidenceRecord:
    return EvidenceRecord(evidence_id, "goal-1", subgoal_id, "scanner", {"ok": True}, "2026-06-09T00:00:00Z")


def test_repository_adds_and_queries_evidence(tmp_path: Path) -> None:
    repository = EvidenceRepository(tmp_path)
    record = repository.add_record(_record("e-1"))
    assert repository.get_record("e-1") == record
    assert repository.list_by_goal("goal-1") == [record]
    assert repository.list_by_subgoal("sub-1") == [record]


def test_repository_queries_latest_validated_evidence_by_goal_and_subgoal(tmp_path: Path) -> None:
    repository = EvidenceRepository(tmp_path)
    pending = _record("e-1")
    repository.add_record(pending)
    validated = EvidenceValidator().validate(pending, accepted=True)
    repository.add_record(validated)
    repository.add_record(_record("e-2"))
    assert repository.list_validated_by_goal("goal-1") == [validated]
    assert repository.list_validated_by_subgoal("sub-1") == [validated]


def test_evidence_repository_does_not_modify_goal_repository(tmp_path: Path) -> None:
    goals = GoalRepository(tmp_path)
    goals.append_goal(PersistentGoal("goal-1", "Goal", status="active"))
    before = goals.storage_path.read_bytes()
    EvidenceRepository(tmp_path).add_record(_record("e-1", subgoal_id=None))
    assert goals.storage_path.read_bytes() == before

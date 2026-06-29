from __future__ import annotations

from pathlib import Path

from core.evidence.evidence_record import EvidenceRecord
from core.evidence.evidence_repository import EvidenceRepository
import pytest

pytestmark = [pytest.mark.contract]




def _record(evidence_id: str, state: str = "validated") -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        goal_id="goal_a",
        subgoal_id="subgoal_a",
        source="runtime_result",
        summary={"ok": True},
        timestamp="2026-01-01T00:00:00+00:00",
        validation_state=state,
    )


def test_repository_persists_and_queries_without_validating(tmp_path: Path) -> None:
    repository = EvidenceRepository(tmp_path)
    pending = repository.add_record(_record("evidence_pending", "pending"))
    validated = repository.add_record(_record("evidence_validated", "validated"))

    assert pending.validation_state == "pending"
    assert validated.validation_state == "validated"
    assert repository.list_validated_by_goal("goal_a") == []


def test_repository_has_no_validation_or_goal_completion_authority(tmp_path: Path) -> None:
    repository = EvidenceRepository(tmp_path)

    assert not hasattr(repository, "validate")
    assert not hasattr(repository, "complete_goal")
    assert not hasattr(repository, "update_goal")
    assert not hasattr(repository, "decide")

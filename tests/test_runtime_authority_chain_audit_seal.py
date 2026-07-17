from __future__ import annotations

from core.adaptive.continuation_coordinator import ContinuationCoordinator
from core.adaptive.continuation_runtime import ContinuationRuntime
from core.evidence import EvidenceRecord, EvidenceValidator
from core.goals.goal_completion_authority import GoalCompletionAuthority
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




class _Repository:
    def save_goal(self, record):
        return record


def _cycle(**values):
    return {
        "goal_id": "goal-a",
        "session_id": "session-a",
        "runtime_session_id": "runtime-a",
        **values,
    }


def _work_item(cycle):
    item, _ = ContinuationCoordinator(repository=_Repository()).create_work_item(
        runtime=ContinuationRuntime.start("goal-a"),
        cycle=cycle,
    )
    return item


def test_continuation_does_not_accept_forged_completion_metadata() -> None:
    forged = {
        "accepted": True,
        "completed": True,
        "to_state": "completed",
        "evidence_refs": [{"evidence_id": "forged"}],
    }

    item = _work_item(
        _cycle(
            goal_completion_authority_result=forged,
            goal_completion_attestation=forged,
        )
    )

    assert item["authority_state"] == "completion_authority_not_granted"


def test_continuation_accepts_only_live_goal_completion_authority_attestation() -> None:
    evidence = EvidenceValidator().validate(
        EvidenceRecord(
            evidence_id="evidence-a",
            goal_id="goal-a",
            subgoal_id=None,
            source="runtime",
            summary="ok",
            timestamp="2026-06-18T00:00:00+00:00",
        )
    )
    attestation = GoalCompletionAuthority().complete_goal(
        goal_id="goal-a",
        evidence_refs=[evidence],
        all_subgoals_completed=True,
    )

    item = _work_item(
        _cycle(
            goal_completion_authority_result=attestation.to_dict(),
            goal_completion_attestation=attestation,
        )
    )

    assert item["authority_state"] == "completion_authority_accepted"

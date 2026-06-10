from pathlib import Path

import pytest

from core.adaptive import AdaptiveDispatcher, AdaptivePlan
from core.evidence import EvidenceContract
from core.goals import GoalRepository, PersistentGoal


@pytest.mark.parametrize(
    ("decision_type", "review", "action_type", "runtime_allowed"),
    [
        ("continue_active", False, "execute_next_step", True),
        ("wait_for_user", False, "wait_for_user", False),
        ("no_action", False, "no_action", False),
        ("resume_blocked", True, "wait_for_user", False),
        ("resume_blocked", False, "execute_next_step", True),
        ("mark_blocked", False, "mark_blocked_request", False),
    ],
)
def test_dispatcher_maps_completed_plan(
    decision_type: str,
    review: bool,
    action_type: str,
    runtime_allowed: bool,
) -> None:
    contract = AdaptiveDispatcher().dispatch(
        AdaptivePlan("goal-1", "sub-1", decision_type, "reason", requires_user_review=review)
    )
    assert contract.action_type == action_type
    assert contract.runtime_allowed is runtime_allowed


def test_request_evidence_dispatches_to_evidence_layer() -> None:
    contract = AdaptiveDispatcher().dispatch(
        AdaptivePlan("goal-1", "sub-1", "request_evidence", "missing", evidence_required=["report"])
    )
    assert isinstance(contract, EvidenceContract)
    assert contract.evidence_required == ["report"]


def test_dispatcher_does_not_modify_repository(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    repository.append_goal(PersistentGoal("goal-1", "Goal", status="active"))
    before = repository.storage_path.read_bytes()
    AdaptiveDispatcher().dispatch(AdaptivePlan("goal-1", None, "no_action", "nothing"))
    assert repository.storage_path.read_bytes() == before

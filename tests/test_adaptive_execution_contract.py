import pytest

from core.adaptive import AdaptiveExecutionContract
pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def test_execution_contract_contains_required_fields() -> None:
    contract = AdaptiveExecutionContract(
        "plan-1",
        "goal-1",
        "sub-1",
        "continue_active",
        "execute_next_step",
        "continue",
        runtime_allowed=True,
    )
    assert contract.to_dict()["runtime_allowed"] is True
    assert contract.to_dict()["action_type"] == "execute_next_step"


def test_review_contract_cannot_allow_runtime() -> None:
    with pytest.raises(ValueError, match="review_cannot_allow_runtime"):
        AdaptiveExecutionContract(
            "plan-1",
            "goal-1",
            "sub-1",
            "resume_blocked",
            "execute_next_step",
            "resume",
            requires_user_review=True,
            runtime_allowed=True,
        )


def test_request_evidence_cannot_be_forged_as_runtime_contract() -> None:
    with pytest.raises(ValueError, match="requires_evidence_contract"):
        AdaptiveExecutionContract(
            "plan-1",
            "goal-1",
            None,
            "request_evidence",
            "execute_next_step",
            "unsafe",
            runtime_allowed=True,
        )

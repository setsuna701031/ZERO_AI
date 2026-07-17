from core.tasks.engineering_lifecycle_transition import EngineeringLifecycleTransition
from core.tasks.engineering_lifecycle_validator import EngineeringLifecycleValidator


def test_engineering_lifecycle_validator_accepts_legal_transition():
    result = EngineeringLifecycleValidator().validate(EngineeringLifecycleTransition("running", "continuing", "continue"))
    assert result.accepted is True


def test_engineering_lifecycle_validator_rejects_terminal_backtracking():
    result = EngineeringLifecycleValidator().validate({"from_state": "completed", "to_state": "running"})
    assert result.accepted is False
    assert "illegal_transition" in result.blocked_reason

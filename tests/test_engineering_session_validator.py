from core.session.engineering_session_validator import EngineeringSessionValidator


def test_validator_accepts_and_rejects_transitions():
    validator = EngineeringSessionValidator()
    assert validator.validate({"from_state": "created", "to_state": "active"}).accepted is True
    rejected = validator.validate({"from_state": "completed", "to_state": "active"})
    assert rejected.accepted is False
    assert "completed->active" in rejected.blocked_reason

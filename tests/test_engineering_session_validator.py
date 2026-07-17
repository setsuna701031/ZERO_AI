from core.session.engineering_session_transition import ENGINEERING_SESSION_TRANSITION_SCHEMA
from core.session.engineering_session_validator import EngineeringSessionValidator


def test_validator_accepts_and_rejects_transitions():
    validator = EngineeringSessionValidator()
    record = {
        "from_state": "created",
        "to_state": "active",
        "schema": ENGINEERING_SESSION_TRANSITION_SCHEMA,
        "reason": "start",
        "trigger": "session_start",
        "evidence": {},
        "source": "test",
        "created_at": "2026-06-11T00:00:00+00:00",
        "session_id": "session-1",
    }
    assert validator.validate(record).accepted is True
    rejected = validator.validate({**record, "from_state": "completed"})
    assert rejected.accepted is False
    assert "completed->active" in rejected.blocked_reason

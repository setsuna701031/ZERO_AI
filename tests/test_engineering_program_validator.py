from core.program.engineering_program_validator import EngineeringProgramValidator


def test_engineering_program_validator_rejects_archived_escape() -> None:
    result = EngineeringProgramValidator().validate({"from_state": "archived", "to_state": "active"})
    assert result.accepted is False
    assert "illegal_transition" in result.blocked_reason

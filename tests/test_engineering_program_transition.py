from core.program.engineering_program_transition import EngineeringProgramTransition


def test_engineering_program_transition_to_dict() -> None:
    transition = EngineeringProgramTransition("created", "active", "active", "start")
    record = transition.to_dict()
    assert record["from_state"] == "created"
    assert record["to_state"] == "active"
    assert record["execution_path"]["mutates_memory"] is False

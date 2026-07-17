from core.program.engineering_program_state import EngineeringProgramState, clean_engineering_program_state


def test_engineering_program_state_values() -> None:
    assert EngineeringProgramState.CREATED.value == "created"
    assert clean_engineering_program_state("ACTIVE") == "active"

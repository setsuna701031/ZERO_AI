from core.session.engineering_session_state import EngineeringSessionState, clean_engineering_session_state


def test_engineering_session_state_values():
    assert clean_engineering_session_state("created") == EngineeringSessionState.CREATED.value
    assert clean_engineering_session_state(EngineeringSessionState.ACTIVE) == "active"

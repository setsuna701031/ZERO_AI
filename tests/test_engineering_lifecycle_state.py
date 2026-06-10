import pytest

from core.tasks.engineering_lifecycle_state import EngineeringLifecycleState, clean_engineering_lifecycle_state


def test_clean_engineering_lifecycle_state_accepts_known_state():
    assert clean_engineering_lifecycle_state(EngineeringLifecycleState.RUNNING) == "running"
    assert clean_engineering_lifecycle_state("completed") == "completed"


def test_clean_engineering_lifecycle_state_rejects_unknown_state():
    with pytest.raises(ValueError):
        clean_engineering_lifecycle_state("done-ish")

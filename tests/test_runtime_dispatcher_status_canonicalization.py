from core.runtime.runtime_dispatcher import (
    RUNTIME_LIFECYCLE_STATES,
    RUNTIME_TERMINAL_STATES,
    RuntimeDispatcher,
    normalize_runtime_dispatcher_status,
    validate_runtime_transition,
)


def test_runtime_dispatcher_canonical_lifecycle_states_use_finished() -> None:
    assert "finished" in RUNTIME_LIFECYCLE_STATES
    assert "completed" not in RUNTIME_LIFECYCLE_STATES
    assert RUNTIME_TERMINAL_STATES == frozenset({"failed", "finished"})


def test_runtime_dispatcher_normalizes_success_aliases_to_finished() -> None:
    for alias in ("completed", "done", "success", "complete"):
        assert normalize_runtime_dispatcher_status(alias) == "finished"
    assert normalize_runtime_dispatcher_status("failed") == "failed"


def test_runtime_dispatcher_step_feedback_projects_aliases_to_finished() -> None:
    task = {"steps": [{"id": "step-1", "type": "unit"}], "current_step_index": 1}
    for alias in ("completed", "done", "success", "complete"):
        feedback = RuntimeDispatcher._step_feedback(
            task=task,
            result={"ok": True, "status": alias, "current_step_index": 1},
            tick=0,
        )
        assert feedback["ok"] is True
        assert feedback["runtime_status"] == "finished"
        assert feedback["next_action"] == "complete"


def test_runtime_dispatcher_failed_status_remains_failed() -> None:
    feedback = RuntimeDispatcher._step_feedback(
        task={"steps": [{"id": "step-1"}], "current_step_index": 0},
        result={"ok": False, "status": "failed", "error": "boom"},
        tick=0,
    )
    assert feedback["ok"] is False
    assert feedback["runtime_status"] == "failed"
    assert feedback["next_action"] == "fail"


def test_runtime_dispatcher_transition_accepts_completed_alias_to_finished() -> None:
    assert validate_runtime_transition("executing", "completed") is True
    assert validate_runtime_transition("executing", "finished") is True
    assert validate_runtime_transition("finished", "executing") is False

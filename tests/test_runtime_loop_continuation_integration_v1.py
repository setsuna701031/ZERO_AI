from core.runtime.runtime_loop_continuation import (
    LOOP_CONTINUATION_STATUS_BLOCKED,
    LOOP_CONTINUATION_STATUS_RESUMED,
    LOOP_CONTINUATION_STATUS_SKIPPED,
    prepare_runtime_loop_continuation_after_failure,
)


class FakeTaskRuntime:
    def __init__(self):
        self.calls = []

    def apply_runtime_transition(
        self,
        task,
        state,
        *,
        owner,
        action,
        updates,
        save=False,
        allow_terminal_write=False,
    ):
        self.calls.append(
            {
                "owner": owner,
                "action": action,
                "updates": updates,
            }
        )
        next_state = dict(state)
        next_state.update(updates)
        return next_state


def test_loop_continuation_resumes_after_recovered_step_failure():
    runtime = FakeTaskRuntime()

    result = prepare_runtime_loop_continuation_after_failure(
        task_runtime=runtime,
        task={"id": "task-1"},
        runtime_state={
            "session_id": "session-1",
            "task_id": "task-1",
            "status": "failed",
            "current_step_index": 1,
            "steps_total": 3,
        },
        step={"type": "tool"},
        execution_result={"ok": False, "error": "tool_failed"},
        metadata={"recovery_id": "recovery-1"},
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["status"] == LOOP_CONTINUATION_STATUS_RESUMED
    assert payload["resumed"] is True
    assert payload["next_step_index"] == 1
    assert payload["next_action"] == "run_next_step"
    assert payload["loop_patch"]["last_decision"] == "resume_after_recovery"
    assert payload["resumed_state"]["status"] == "running"
    assert len(runtime.calls) == 1


def test_loop_continuation_blocks_rollback_required_failure():
    runtime = FakeTaskRuntime()

    result = prepare_runtime_loop_continuation_after_failure(
        task_runtime=runtime,
        task={"id": "task-rollback"},
        runtime_state={
            "session_id": "session-rollback",
            "task_id": "task-rollback",
            "status": "failed",
            "current_step_index": 2,
            "steps_total": 5,
            "rollback_required": True,
        },
        step={"type": "mutation"},
        execution_result={
            "ok": False,
            "error": "mutation_failed",
            "rollback_required": True,
        },
        metadata={"recovery_id": "recovery-rollback"},
    )

    payload = result.to_dict()

    assert payload["status"] == LOOP_CONTINUATION_STATUS_BLOCKED
    assert payload["resumed"] is False
    assert payload["next_action"] == "wait_for_recovery_approval"
    assert payload["loop_patch"] == {}
    assert len(runtime.calls) == 0


def test_loop_continuation_can_be_disabled():
    runtime = FakeTaskRuntime()

    result = prepare_runtime_loop_continuation_after_failure(
        task_runtime=runtime,
        task={"id": "task-disabled"},
        runtime_state={
            "session_id": "session-disabled",
            "task_id": "task-disabled",
            "status": "failed",
            "current_step_index": 0,
            "steps_total": 1,
        },
        step={"type": "tool"},
        execution_result={"ok": False, "error": "disabled"},
        enabled=False,
    )

    payload = result.to_dict()

    assert payload["status"] == LOOP_CONTINUATION_STATUS_SKIPPED
    assert payload["resumed"] is False
    assert payload["next_action"] == "recovery_continuation_disabled"
    assert len(runtime.calls) == 0


def test_loop_continuation_preserves_original_runtime_state_snapshot():
    runtime = FakeTaskRuntime()
    state = {
        "session_id": "session-source",
        "task_id": "task-source",
        "status": "failed",
        "current_step_index": 1,
        "steps_total": 2,
    }

    result = prepare_runtime_loop_continuation_after_failure(
        task_runtime=runtime,
        task={"id": "task-source"},
        runtime_state=state,
        step={"type": "tool"},
        execution_result={"ok": False, "error": "source"},
        metadata={"recovery_id": "recovery-source"},
    )

    assert result.resumed is True
    assert state["status"] == "failed"
    assert result.resumed_state["status"] == "running"


def test_loop_continuation_routes_through_authority_before_resume():
    runtime = FakeTaskRuntime()

    result = prepare_runtime_loop_continuation_after_failure(
        task_runtime=runtime,
        task={"id": "task-authority"},
        runtime_state={
            "session_id": "session-authority",
            "task_id": "task-authority",
            "status": "failed",
        },
        step={"type": "tool"},
        execution_result={"ok": False, "error": "authority"},
    )

    assert result.resumed is True
    assert runtime.calls[0]["owner"] == "runtime_recovery_authority"

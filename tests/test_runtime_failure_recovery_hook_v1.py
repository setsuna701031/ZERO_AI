from core.runtime.runtime_failure_recovery_hook import (
    FAILURE_HOOK_STATUS_RECOVERY_APPLIED,
    FAILURE_HOOK_STATUS_RECOVERY_BLOCKED,
    FAILURE_HOOK_STATUS_SKIPPED,
    handle_runtime_failure_with_recovery,
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
                "task": task,
                "state": state,
                "owner": owner,
                "action": action,
                "updates": updates,
                "save": save,
                "allow_terminal_write": allow_terminal_write,
            }
        )
        next_state = dict(state)
        next_state.update(updates)
        next_state["last_transition_owner"] = owner
        next_state["last_transition_action"] = action
        return next_state


def test_failure_hook_recovers_simple_step_failure_through_authority():
    task_runtime = FakeTaskRuntime()

    result = handle_runtime_failure_with_recovery(
        task_runtime=task_runtime,
        task={"id": "task-1", "name": "Task 1"},
        current_state={
            "session_id": "session-1",
            "status": "failed",
            "task_id": "task-1",
        },
        step={"type": "tool"},
        step_result={"ok": False, "error": "tool_error"},
        metadata={"recovery_id": "recovery-1"},
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["status"] == FAILURE_HOOK_STATUS_RECOVERY_APPLIED
    assert payload["recovered"] is True
    assert payload["runtime_state_patch"]["status"] == "running"
    assert len(task_runtime.calls) == 1
    assert task_runtime.calls[0]["owner"] == "runtime_recovery_authority"


def test_failure_hook_blocks_unapproved_rollback_failure():
    task_runtime = FakeTaskRuntime()

    result = handle_runtime_failure_with_recovery(
        task_runtime=task_runtime,
        task={"id": "task-rollback"},
        current_state={
            "session_id": "session-rollback",
            "status": "failed",
            "rollback_required": True,
        },
        step={"type": "mutation"},
        step_result={
            "ok": False,
            "error": "mutation_failed",
            "rollback_required": True,
        },
        metadata={"recovery_id": "recovery-rollback"},
    )

    payload = result.to_dict()

    assert payload["status"] == FAILURE_HOOK_STATUS_RECOVERY_BLOCKED
    assert payload["recovered"] is False
    assert payload["failure"]["rollback_required"] is True
    assert len(task_runtime.calls) == 0


def test_failure_hook_can_be_disabled_without_mutating_runtime():
    task_runtime = FakeTaskRuntime()

    result = handle_runtime_failure_with_recovery(
        task_runtime=task_runtime,
        task={"id": "task-disabled"},
        current_state={"session_id": "session-disabled", "status": "failed"},
        step_result={"ok": False, "error": "disabled"},
        metadata={"recovery_id": "recovery-disabled"},
        auto_recover=False,
    )

    payload = result.to_dict()

    assert payload["status"] == FAILURE_HOOK_STATUS_SKIPPED
    assert payload["recovered"] is False
    assert payload["reason"] == "auto_recover_disabled"
    assert len(task_runtime.calls) == 0


def test_failure_hook_preserves_source_state_snapshot():
    task_runtime = FakeTaskRuntime()
    state = {
        "session_id": "session-source",
        "status": "failed",
    }

    result = handle_runtime_failure_with_recovery(
        task_runtime=task_runtime,
        task={"id": "task-source"},
        current_state=state,
        step_result={"ok": False, "error": "source"},
        metadata={"recovery_id": "recovery-source"},
    )

    assert result.recovered is True
    assert state["status"] == "failed"
    assert len(task_runtime.calls) == 1
    assert task_runtime.calls[0]["state"]["status"] == "failed"


def test_failure_hook_passes_save_and_terminal_flags_to_authority():
    task_runtime = FakeTaskRuntime()

    result = handle_runtime_failure_with_recovery(
        task_runtime=task_runtime,
        task={"id": "task-flags"},
        current_state={"session_id": "session-flags", "status": "failed"},
        step_result={"ok": False, "error": "flags"},
        metadata={"recovery_id": "recovery-flags"},
        save=True,
        allow_terminal_write=True,
    )

    assert result.recovered is True
    assert len(task_runtime.calls) == 1
    assert task_runtime.calls[0]["save"] is True
    assert task_runtime.calls[0]["allow_terminal_write"] is True

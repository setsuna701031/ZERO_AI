from core.runtime.runtime_task_failure_auto_recovery import (
    AUTO_RECOVERY_STATUS_APPLIED,
    AUTO_RECOVERY_STATUS_BLOCKED,
    AUTO_RECOVERY_STATUS_SKIPPED,
    auto_recover_mark_failed_result,
    auto_recover_record_step_failure_result,
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


def test_record_step_failure_auto_recovers_via_task_runtime_authority():
    task_runtime = FakeTaskRuntime()
    result = auto_recover_record_step_failure_result(
        task_runtime=task_runtime,
        task={"id": "task-1", "name": "Task 1"},
        step={"type": "tool"},
        step_result={"ok": False, "error": "tool_error"},
        record_result={
            "ok": False,
            "status": "failed",
            "runtime_state": {
                "session_id": "session-1",
                "task_id": "task-1",
                "status": "failed",
            },
        },
        metadata={"recovery_id": "recovery-1"},
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["status"] == AUTO_RECOVERY_STATUS_APPLIED
    assert payload["recovered"] is True
    assert payload["runtime_state_patch"]["status"] == "running"
    assert payload["final_runtime_state"]["status"] == "running"
    assert len(task_runtime.calls) == 1
    assert task_runtime.calls[0]["owner"] == "runtime_recovery_authority"


def test_mark_failed_auto_recovers_via_same_bridge():
    task_runtime = FakeTaskRuntime()
    result = auto_recover_mark_failed_result(
        task_runtime=task_runtime,
        task={"id": "task-failed"},
        mark_failed_result={
            "ok": False,
            "status": "failed",
            "failure_type": "tool_error",
            "failure_message": "tool failed",
            "runtime_state": {
                "session_id": "session-failed",
                "task_id": "task-failed",
                "status": "failed",
            },
        },
        metadata={"recovery_id": "recovery-failed"},
    )

    payload = result.to_dict()

    assert payload["status"] == AUTO_RECOVERY_STATUS_APPLIED
    assert payload["recovered"] is True
    assert payload["final_runtime_state"]["status"] == "running"
    assert len(task_runtime.calls) == 1


def test_auto_recovery_blocks_rollback_required_failure():
    task_runtime = FakeTaskRuntime()
    result = auto_recover_record_step_failure_result(
        task_runtime=task_runtime,
        task={"id": "task-rollback"},
        step={"type": "mutation"},
        step_result={
            "ok": False,
            "error": "mutation_failed",
            "rollback_required": True,
        },
        record_result={
            "ok": False,
            "status": "failed",
            "runtime_state": {
                "session_id": "session-rollback",
                "task_id": "task-rollback",
                "status": "failed",
                "rollback_required": True,
            },
        },
        metadata={"recovery_id": "recovery-rollback"},
    )

    payload = result.to_dict()

    assert payload["status"] == AUTO_RECOVERY_STATUS_BLOCKED
    assert payload["recovered"] is False
    assert len(task_runtime.calls) == 0


def test_auto_recovery_can_be_disabled():
    task_runtime = FakeTaskRuntime()
    result = auto_recover_record_step_failure_result(
        task_runtime=task_runtime,
        task={"id": "task-disabled"},
        step={"type": "tool"},
        step_result={"ok": False, "error": "disabled"},
        record_result={
            "ok": False,
            "status": "failed",
            "runtime_state": {
                "session_id": "session-disabled",
                "task_id": "task-disabled",
                "status": "failed",
            },
        },
        metadata={"recovery_id": "recovery-disabled"},
        enabled=False,
    )

    payload = result.to_dict()

    assert payload["status"] == AUTO_RECOVERY_STATUS_SKIPPED
    assert payload["recovered"] is False
    assert payload["reason"] == "task_runtime_auto_recovery_disabled"
    assert len(task_runtime.calls) == 0


def test_auto_recovery_preserves_original_record_result_snapshot():
    task_runtime = FakeTaskRuntime()
    record_result = {
        "ok": False,
        "status": "failed",
        "runtime_state": {
            "session_id": "session-source",
            "task_id": "task-source",
            "status": "failed",
        },
    }

    result = auto_recover_record_step_failure_result(
        task_runtime=task_runtime,
        task={"id": "task-source"},
        step={"type": "tool"},
        step_result={"ok": False, "error": "source"},
        record_result=record_result,
        metadata={"recovery_id": "recovery-source"},
    )

    assert result.recovered is True
    assert record_result["runtime_state"]["status"] == "failed"
    assert result.original_result["runtime_state"]["status"] == "failed"
    assert result.final_runtime_state["status"] == "running"


def test_auto_recovery_forwards_save_and_terminal_write_flags():
    task_runtime = FakeTaskRuntime()
    result = auto_recover_record_step_failure_result(
        task_runtime=task_runtime,
        task={"id": "task-flags"},
        step={"type": "tool"},
        step_result={"ok": False, "error": "flags"},
        record_result={
            "ok": False,
            "status": "failed",
            "runtime_state": {
                "session_id": "session-flags",
                "task_id": "task-flags",
                "status": "failed",
            },
        },
        metadata={"recovery_id": "recovery-flags"},
        save=True,
        allow_terminal_write=True,
    )

    assert result.recovered is True
    assert len(task_runtime.calls) == 1
    assert task_runtime.calls[0]["save"] is True
    assert task_runtime.calls[0]["allow_terminal_write"] is True

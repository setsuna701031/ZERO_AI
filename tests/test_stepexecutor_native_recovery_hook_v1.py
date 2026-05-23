from core.runtime.runtime_step_executor_native_recovery import (
    NATIVE_HOOK_STATUS_BLOCKED,
    NATIVE_HOOK_STATUS_RECOVERED,
    NATIVE_HOOK_STATUS_SKIPPED,
    handle_step_executor_failure_with_recovery,
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


def test_native_hook_recovers_step_execution_failure():
    runtime = FakeTaskRuntime()

    result = handle_step_executor_failure_with_recovery(
        task_runtime=runtime,
        task={"id": "task-1"},
        runtime_state={
            "session_id": "session-1",
            "task_id": "task-1",
            "status": "failed",
        },
        step={"type": "tool"},
        execution_result={
            "ok": False,
            "error": "tool_failed",
        },
        metadata={"recovery_id": "recovery-1"},
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["status"] == NATIVE_HOOK_STATUS_RECOVERED
    assert payload["recovered"] is True
    assert payload["final_runtime_state"]["status"] == "running"
    assert len(runtime.calls) == 1


def test_native_hook_blocks_rollback_required_failures():
    runtime = FakeTaskRuntime()

    result = handle_step_executor_failure_with_recovery(
        task_runtime=runtime,
        task={"id": "task-rollback"},
        runtime_state={
            "session_id": "session-rollback",
            "task_id": "task-rollback",
            "status": "failed",
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

    assert payload["status"] == NATIVE_HOOK_STATUS_BLOCKED
    assert payload["recovered"] is False
    assert len(runtime.calls) == 0


def test_native_hook_can_be_disabled():
    runtime = FakeTaskRuntime()

    result = handle_step_executor_failure_with_recovery(
        task_runtime=runtime,
        task={"id": "task-disabled"},
        runtime_state={
            "session_id": "session-disabled",
            "task_id": "task-disabled",
            "status": "failed",
        },
        step={"type": "tool"},
        execution_result={
            "ok": False,
            "error": "disabled",
        },
        enabled=False,
    )

    payload = result.to_dict()

    assert payload["status"] == NATIVE_HOOK_STATUS_SKIPPED
    assert payload["recovered"] is False
    assert len(runtime.calls) == 0


def test_native_hook_preserves_execution_result_snapshot():
    runtime = FakeTaskRuntime()

    execution_result = {
        "ok": False,
        "error": "snapshot_error",
    }

    result = handle_step_executor_failure_with_recovery(
        task_runtime=runtime,
        task={"id": "task-snapshot"},
        runtime_state={
            "session_id": "session-snapshot",
            "task_id": "task-snapshot",
            "status": "failed",
        },
        step={"type": "tool"},
        execution_result=execution_result,
    )

    assert result.recovered is True
    assert execution_result["error"] == "snapshot_error"
    assert result.execution_result["error"] == "snapshot_error"


def test_native_hook_routes_through_runtime_authority():
    runtime = FakeTaskRuntime()

    result = handle_step_executor_failure_with_recovery(
        task_runtime=runtime,
        task={"id": "task-authority"},
        runtime_state={
            "session_id": "session-authority",
            "task_id": "task-authority",
            "status": "failed",
        },
        step={"type": "tool"},
        execution_result={
            "ok": False,
            "error": "authority_error",
        },
    )

    assert result.recovered is True
    assert runtime.calls[0]["owner"] == "runtime_recovery_authority"

from core.runtime.runtime_recovery_authority import (

    AUTHORITY_APPLY_STATUS_APPLIED,
    AUTHORITY_APPLY_STATUS_BLOCKED,
    AUTHORITY_APPLY_STATUS_REVIEW_REQUIRED,
    apply_recovery_pipeline_transition,
    run_recovery_pipeline_and_apply_transition,
)
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy, pytest.mark.integration]



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


def test_authority_applies_ready_to_continue_patch_through_task_runtime():
    task_runtime = FakeTaskRuntime()
    result = apply_recovery_pipeline_transition(
        task_runtime=task_runtime,
        task={"id": "task-1"},
        current_state={"status": "failed", "session_id": "session-1"},
        pipeline_result={
            "recovery_id": "recovery-1",
            "source_session_id": "session-1",
            "final_status": "ready_to_continue",
            "runtime_state_patch": {
                "status": "running",
                "recovery_status": "ready_to_continue",
                "next_action": "resume_runtime",
            },
        },
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["status"] == AUTHORITY_APPLY_STATUS_APPLIED
    assert payload["applied"] is True
    assert len(task_runtime.calls) == 1
    assert task_runtime.calls[0]["owner"] == "runtime_recovery_authority"
    assert payload["applied_state"]["status"] == "running"
    assert payload["applied_state"]["last_transition_action"] == "apply_recovery_runtime_state_patch"


def test_authority_does_not_apply_blocked_pipeline_patch():
    task_runtime = FakeTaskRuntime()
    result = apply_recovery_pipeline_transition(
        task_runtime=task_runtime,
        task={"id": "task-blocked"},
        current_state={"status": "failed", "session_id": "session-blocked"},
        pipeline_result={
            "recovery_id": "recovery-blocked",
            "source_session_id": "session-blocked",
            "final_status": "blocked",
            "runtime_state_patch": {
                "status": "blocked",
                "recovery_status": "blocked",
                "next_action": "wait_for_recovery_approval",
            },
        },
    )

    payload = result.to_dict()

    assert payload["status"] == AUTHORITY_APPLY_STATUS_BLOCKED
    assert payload["applied"] is False
    assert len(task_runtime.calls) == 0
    assert payload["reason"] == "pipeline_blocked"


def test_authority_does_not_apply_review_required_pipeline_patch():
    task_runtime = FakeTaskRuntime()
    result = apply_recovery_pipeline_transition(
        task_runtime=task_runtime,
        task={"id": "task-review"},
        current_state={"status": "failed", "session_id": "session-review"},
        pipeline_result={
            "recovery_id": "recovery-review",
            "source_session_id": "session-review",
            "final_status": "review_required",
            "runtime_state_patch": {
                "status": "waiting_review",
                "recovery_status": "review_required",
                "next_action": "wait_for_recovery_review",
            },
        },
    )

    payload = result.to_dict()

    assert payload["status"] == AUTHORITY_APPLY_STATUS_REVIEW_REQUIRED
    assert payload["applied"] is False
    assert len(task_runtime.calls) == 0
    assert payload["reason"] == "pipeline_review_required"


def test_run_pipeline_and_apply_transition_uses_pipeline_result():
    task_runtime = FakeTaskRuntime()
    result = run_recovery_pipeline_and_apply_transition(
        task_runtime=task_runtime,
        task={"id": "task-pipeline"},
        current_state={"status": "failed", "session_id": "session-pipeline"},
        source_failure={"error": "tool_error"},
        metadata={"recovery_id": "recovery-pipeline"},
    )

    payload = result.to_dict()

    assert payload["status"] == AUTHORITY_APPLY_STATUS_APPLIED
    assert payload["applied"] is True
    assert payload["recovery_id"] == "recovery-pipeline"
    assert len(task_runtime.calls) == 1
    assert task_runtime.calls[0]["updates"]["status"] == "running"


def test_run_pipeline_and_apply_transition_blocks_unapproved_rollback():
    task_runtime = FakeTaskRuntime()
    result = run_recovery_pipeline_and_apply_transition(
        task_runtime=task_runtime,
        task={"id": "task-rollback"},
        current_state={
            "status": "failed",
            "session_id": "session-rollback",
            "rollback_required": True,
        },
        source_failure={
            "error": "mutation_failed",
            "rollback_required": True,
        },
        metadata={"recovery_id": "recovery-rollback"},
    )

    payload = result.to_dict()

    assert payload["status"] == AUTHORITY_APPLY_STATUS_BLOCKED
    assert payload["applied"] is False
    assert len(task_runtime.calls) == 0

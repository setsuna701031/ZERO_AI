from __future__ import annotations

import pytest

from core.runtime.runtime_state_machine import RuntimeStateMachine
from core.runtime.runtime_transition_policy import RuntimeTransitionPolicyError
from core.runtime.task_runtime import TaskRuntime
pytestmark = [pytest.mark.contract]




def _task(tmp_path, *, task_id: str = "status-canon") -> dict:
    task_dir = tmp_path / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "runtime status canonicalization",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [],
    }


def test_runtime_state_machine_canonicalizes_executor_persistent_and_aer_status_aliases() -> None:
    machine = RuntimeStateMachine()

    assert machine.normalize_status("success") == "finished"
    assert machine.normalize_status("succeeded") == "finished"
    assert machine.normalize_status("completed") == "finished"
    assert machine.normalize_status("recoverable_failure") == "failed"
    assert machine.normalize_status("partial_failed") == "failed"
    assert machine.normalize_status("review_required") == "blocked"
    assert machine.normalize_status("policy_blocked") == "blocked"
    assert machine.normalize_status("forced_repair") == "replanning"
    assert machine.normalize_status("fallback") == "replanning"
    assert machine.normalize_status("timed_out") == "timeout"
    assert machine.normalize_status("aborted") == "cancelled"


def test_task_runtime_transition_accepts_aliases_only_through_canonical_state_machine(tmp_path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path)
    state = runtime.ensure_runtime_state(task)

    finished = runtime.apply_runtime_transition(
        task,
        state,
        owner="task_runtime",
        action="executor_reported_success_alias",
        updates={"status": "success"},
    )

    assert finished["status"] == "finished"
    assert finished["runtime_status_history"][-1]["new_status"] == "finished"
    assert finished["runtime_transition_policy"]["last_decision"]["ok"] is True


def test_terminal_failure_recovery_cannot_be_forged_by_success_or_running_alias(tmp_path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path, task_id="terminal")
    state = runtime.ensure_runtime_state(task)
    running = runtime.apply_runtime_transition(
        task,
        state,
        owner="task_runtime",
        action="start",
        updates={"status": "running"},
    )
    failed = runtime.apply_runtime_transition(
        task,
        running,
        owner="task_runtime",
        action="fail",
        updates={"status": "failed"},
    )

    with pytest.raises(RuntimeTransitionPolicyError):
        runtime.apply_runtime_transition(
            task,
            failed,
            owner="task_runtime",
            action="forged_success_recovery",
            updates={"status": "success"},
        )
    with pytest.raises(RuntimeTransitionPolicyError):
        runtime.apply_runtime_transition(
            task,
            failed,
            owner="task_runtime",
            action="forged_running_recovery",
            updates={"status": "running"},
        )


def test_unknown_status_still_fails_closed_instead_of_becoming_queued(tmp_path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path, task_id="unknown")
    state = runtime.ensure_runtime_state(task)

    with pytest.raises(RuntimeTransitionPolicyError, match="runtime_state_machine_rejected_unknown_status:magic_green"):
        runtime.apply_runtime_transition(
            task,
            state,
            owner="task_runtime",
            action="unknown_status",
            updates={"status": "magic-green"},
        )

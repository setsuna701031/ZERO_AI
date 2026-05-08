from __future__ import annotations

import shutil
from pathlib import Path

from core.runtime.runtime_transition_policy import RuntimeTransitionPolicy, RuntimeTransitionPolicyError
from core.runtime.task_runtime import TaskRuntime


REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT / ".test_tmp" / "runtime_transition_policy_phase1"


def setup_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def teardown_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def _task(task_id: str = "transition_policy_probe") -> dict:
    task_dir = TEST_ROOT / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "runtime transition policy probe",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [{"type": "final_answer", "content": "done"}],
        "current_step_index": 0,
    }


def test_policy_blocks_finished_to_running() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "finished"},
        updates={"status": "running"},
        owner="task_runtime",
        action="mark_running",
    )

    assert decision.ok is False
    assert "terminal runtime status finished cannot transition to running" in decision.reason


def test_policy_blocks_failed_to_running() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "failed"},
        updates={"status": "running"},
        owner="task_runtime",
        action="mark_running",
    )

    assert decision.ok is False
    assert "terminal runtime status failed cannot transition to running" in decision.reason


def test_policy_blocks_blocked_to_running_without_unblock_action() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "blocked"},
        updates={"status": "running"},
        owner="task_runtime",
        action="mark_running",
    )

    assert decision.ok is False
    assert "requires explicit unblock/replan action" in decision.reason


def test_policy_allows_blocked_to_running_with_unblock_action() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "blocked"},
        updates={"status": "running"},
        owner="task_runtime",
        action="remove_blocker_unblock",
    )

    assert decision.ok is True


def test_policy_blocks_readonly_runtime_to_running() -> None:
    decision = RuntimeTransitionPolicy().check_transition(
        current_state={"status": "queued", "runtime_mode": "replay"},
        updates={"status": "running"},
        owner="task_runtime",
        action="mark_running",
    )

    assert decision.ok is False
    assert "replay runtime cannot transition to execution status running" in decision.reason


def test_task_runtime_apply_transition_enforces_policy() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task("apply_policy")
    state = runtime.ensure_runtime_state(task)
    state["status"] = "finished"

    try:
        runtime.apply_runtime_transition(
            task,
            state,
            owner="task_runtime",
            action="mark_running",
            updates={"status": "running"},
        )
    except RuntimeTransitionPolicyError as exc:
        assert "terminal runtime status finished cannot transition to running" in str(exc)
    else:
        raise AssertionError("finished -> running should be blocked by transition policy")


def test_task_runtime_apply_transition_records_allowed_policy_decision() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task("apply_allowed_policy")
    state = runtime.ensure_runtime_state(task)

    updated = runtime.apply_runtime_transition(
        task,
        state,
        owner="task_runtime",
        action="mark_running",
        updates={"status": "running"},
    )

    assert updated["status"] == "running"
    decision = updated["runtime_transition_policy"]["last_decision"]
    assert decision["ok"] is True
    assert decision["current_status"] == "queued"
    assert decision["next_status"] == "running"

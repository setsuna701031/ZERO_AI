from __future__ import annotations

import copy
import shutil
from pathlib import Path

from core.runtime.task_runtime import TaskRuntime
from core.runtime.task_runner import TaskRunner


REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT / ".test_tmp" / "runtime_ownership_enforcement_phase2"


def setup_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def teardown_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def _task(task_id: str = "transition_probe") -> dict:
    task_dir = TEST_ROOT / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "runtime ownership transition probe",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [{"type": "final_answer", "content": "done"}],
        "current_step_index": 0,
    }


def test_task_runtime_apply_runtime_transition_sets_owned_fields() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task("apply_transition")
    state = runtime.ensure_runtime_state(task)

    updated = runtime.apply_runtime_transition(
        task,
        state,
        owner="task_runtime",
        action="unit_transition",
        updates={
            "status": "running",
            "next_action": "run_next_tick",
            "last_error": "",
        },
    )

    assert updated["status"] == "running"
    assert updated["next_action"] == "run_next_tick"
    assert updated["last_error"] == ""
    assert updated["runtime_owner"] == "task_runtime"
    assert updated["last_transition_owner"] == "task_runtime"
    assert updated["last_transition_action"] == "unit_transition"


def test_task_runtime_apply_runtime_transition_rejects_task_runner_status_write() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task("reject_runner")
    state = runtime.ensure_runtime_state(task)

    try:
        runtime.apply_runtime_transition(
            task,
            state,
            owner="task_runner",
            action="illegal_status_write",
            updates={"status": "failed"},
        )
    except Exception as exc:
        assert "cannot write section='status'" in str(exc)
    else:
        raise AssertionError("task_runner status write should be rejected")


def test_task_runner_can_use_runtime_transition_funnel_for_owned_status_updates() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    runner = TaskRunner(task_runtime=runtime)

    task = _task("runner_funnel")
    state = runtime.ensure_runtime_state(task)

    updated = runner.runtime.apply_runtime_transition(
        task,
        copy.deepcopy(state),
        owner="task_runtime",
        action="runner_owned_transition",
        updates={
            "status": "blocked",
            "last_error": "blocked by test",
        },
    )

    assert updated["status"] == "blocked"
    assert updated["last_error"] == "blocked by test"
    assert updated["last_transition_action"] == "runner_owned_transition"

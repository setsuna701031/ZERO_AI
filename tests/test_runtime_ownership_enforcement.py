from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.runtime.runtime_state_guard import RuntimeStateGuard, RuntimeStateGuardError
from core.runtime.task_runtime import TaskRuntime


REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT / ".test_tmp" / "runtime_ownership_enforcement"


def setup_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def teardown_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def _task(task_id: str = "ownership_probe") -> dict:
    task_dir = TEST_ROOT / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": "runtime ownership enforcement probe",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [
            {
                "type": "final_answer",
                "content": "done",
            }
        ],
        "current_step_index": 0,
    }


def test_runtime_state_guard_blocks_non_owner_status_write() -> None:
    guard = RuntimeStateGuard()
    state = {"status": "queued"}

    try:
        guard.update_section(
            state,
            section="status",
            owner="task_runner",
            patch="running",
            action="set",
        )
    except RuntimeStateGuardError as exc:
        assert "cannot write section='status'" in str(exc)
    else:
        raise AssertionError("task_runner must not own status writes")


def test_runtime_state_guard_allows_task_runtime_status_write() -> None:
    guard = RuntimeStateGuard()
    result = guard.update_section(
        {"status": "queued"},
        section="status",
        owner="task_runtime",
        patch="running",
        action="set",
    )

    assert result.ok is True
    assert result.state["status"] == "running"
    assert result.owner == "task_runtime"
    assert result.section == "status"


def test_runtime_state_guard_blocks_non_owner_terminal_write() -> None:
    guard = RuntimeStateGuard()

    try:
        guard.update_section(
            {"status": "finished", "execution_trace": []},
            section="execution_trace",
            owner="task_runner",
            patch={"event": "late_write"},
            action="append",
        )
    except RuntimeStateGuardError as exc:
        assert "after terminal status='finished'" in str(exc)
    else:
        raise AssertionError("task_runner must not write after terminal state")


def test_task_runtime_stamps_mark_running_ownership() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task("mark_running_owner")

    result = runtime.mark_running(task, current_tick=1)
    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["status"] == "running"
    assert result["runtime_owner"] == "task_runtime"
    assert result["transition_owner"] == "task_runtime"
    assert result["transition_action"] == "mark_running"
    assert state["runtime_owner"] == "task_runtime"
    assert state["last_transition_owner"] == "task_runtime"
    assert state["last_transition_action"] == "mark_running"


def test_task_runtime_stamps_mark_finished_ownership() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task("mark_finished_owner")

    result = runtime.mark_finished(
        task,
        current_tick=2,
        final_answer="done",
        final_result={"ok": True, "message": "done"},
    )
    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["status"] == "finished"
    assert result["runtime_owner"] == "task_runtime"
    assert result["transition_owner"] == "task_runtime"
    assert result["transition_action"] == "mark_finished"
    assert state["status"] == "finished"
    assert state["runtime_owner"] == "task_runtime"
    assert state["last_transition_action"] == "mark_finished"


def test_task_runtime_stamps_mark_failed_ownership() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task("mark_failed_owner")

    result = runtime.mark_failed(
        task,
        current_tick=3,
        failure_type="internal_error",
        failure_message="probe failed",
    )
    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["status"] == "failed"
    assert state["status"] == "failed"
    assert state["runtime_owner"] == "task_runtime"
    assert state["last_transition_owner"] == "task_runtime"
    assert state["last_transition_action"] == "mark_failed"

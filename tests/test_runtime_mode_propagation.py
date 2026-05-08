from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime
from core.runtime.step_executor import StepExecutor


REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT / ".test_tmp" / "runtime_mode_propagation"


def setup_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def teardown_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def _task(task_id: str, runtime_mode: str, step: dict) -> dict:
    task_dir = TEST_ROOT / "tasks" / task_id
    return {
        "task_id": task_id,
        "task_name": task_id,
        "goal": task_id,
        "status": "queued",
        "runtime_mode": runtime_mode,
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [step],
        "current_step_index": 0,
    }


def test_step_executor_preserves_runtime_mode_in_result_and_trace() -> None:
    executor = StepExecutor(workspace_root=str(TEST_ROOT / "workspace"))
    result = executor.execute_step(
        step={
            "type": "final_answer",
            "runtime_mode": "audit",
            "content": "audit observation complete",
        },
        task={
            "task_id": "audit_read",
            "task_dir": str(TEST_ROOT / "tasks" / "audit_read"),
            "workspace_root": str(TEST_ROOT / "workspace"),
        },
        context={"workspace_root": str(TEST_ROOT / "workspace")},
        step_index=0,
        step_count=1,
    )

    assert result["ok"] is True
    assert result["runtime_mode"] == "audit"
    assert result["step"]["runtime_mode"] == "audit"

    trace = result.get("execution_trace")
    assert isinstance(trace, list)
    assert trace
    assert trace[0]["runtime_mode"] == "audit"


def test_task_runner_propagates_runtime_mode_to_step_executor_result_and_trace() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task(
        "audit_read",
        "audit",
        {
            "type": "final_answer",
            "content": "audit observation complete",
        },
    )

    result = TaskRunner(
        step_executor=StepExecutor(workspace_root=str(TEST_ROOT / "workspace")),
        task_runtime=runtime,
    ).run_task(task, current_tick=1)

    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["status"] == "finished"
    assert state["status"] == "finished"

    execution_log = state.get("execution_log")
    assert isinstance(execution_log, list)
    assert execution_log
    assert execution_log[0]["result"]["runtime_mode"] == "audit"

    trace = state.get("execution_trace")
    assert isinstance(trace, list)
    assert trace
    assert trace[0]["runtime_mode"] == "audit"


def test_task_runner_step_runtime_mode_overrides_task_runtime_mode() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    task = _task(
        "step_override",
        "execute",
        {
            "type": "final_answer",
            "runtime_mode": "replay",
            "content": "replay observation complete",
        },
    )

    result = TaskRunner(
        step_executor=StepExecutor(workspace_root=str(TEST_ROOT / "workspace")),
        task_runtime=runtime,
    ).run_task(task, current_tick=1)

    state = json.loads(Path(task["runtime_state_file"]).read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert result["status"] == "finished"

    execution_log = state.get("execution_log")
    assert isinstance(execution_log, list)
    assert execution_log
    assert execution_log[0]["result"]["runtime_mode"] == "replay"

    trace = state.get("execution_trace")
    assert isinstance(trace, list)
    assert trace
    assert trace[0]["runtime_mode"] == "replay"

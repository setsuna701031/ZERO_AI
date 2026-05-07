from __future__ import annotations

import shutil
from pathlib import Path
import json

from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime


REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = REPO_ROOT / ".test_tmp" / "task_runner_step_advance_persist"


class FakeStepExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute_step(self, **kwargs: object) -> dict:
        step = kwargs["step"]
        step_index = int(kwargs["step_index"])
        assert isinstance(step, dict)

        step_id = str(step.get("id") or "")
        self.calls.append(step_id)
        return {
            "ok": True,
            "step_index": step_index,
            "step_type": step.get("type"),
            "message": f"{step_id} ok",
            "result": {"ok": True, "message": f"{step_id} ok"},
            "execution_trace": [
                {
                    "step_index": step_index,
                    "step_type": step.get("type"),
                    "ok": True,
                    "message": f"{step_id} ok",
                }
            ],
        }


class FailingStepExecutor:
    def execute_step(self, **kwargs: object) -> dict:
        return {
            "ok": False,
            "step_index": int(kwargs["step_index"]),
            "error": "first failed",
            "execution_trace": [
                {
                    "step_index": int(kwargs["step_index"]),
                    "ok": False,
                    "error": "first failed",
                }
            ],
        }


def _task() -> dict:
    task_dir = TEST_ROOT / "tasks" / "two_step_runtime"
    return {
        "task_id": "two_step_runtime",
        "task_name": "two_step_runtime",
        "goal": "verify step advance persists",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [
            {"id": "first", "type": "code_chain_analyze"},
            {"id": "second", "type": "code_chain_verify"},
        ],
        "current_step_index": 0,
        "results": [],
        "step_results": [],
        "execution_log": [],
        "execution_trace": [],
    }


def setup_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def teardown_function() -> None:
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)


def test_successful_step_advances_and_persists_runtime_state() -> None:
    executor = FakeStepExecutor()
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    runner = TaskRunner(step_executor=executor, task_runtime=runtime)

    first_result = runner.run_task(_task(), current_tick=1)
    reloaded_after_first = runtime.load_runtime_state(_task())

    assert first_result["ok"] is True
    assert first_result["action"] == "step_completed"
    assert first_result["current_step_index"] == 1
    assert reloaded_after_first["current_step_index"] == 1
    assert reloaded_after_first["status"] == "running"
    assert executor.calls == ["first"]

    second_result = runner.run_task(_task(), current_tick=2)
    reloaded_after_second = runtime.load_runtime_state(_task())
    runtime_state_json = json.loads(Path(_task()["runtime_state_file"]).read_text(encoding="utf-8"))

    assert second_result["ok"] is True
    assert second_result["action"] == "task_finished"
    assert second_result["status"] == "finished"
    assert reloaded_after_second["current_step_index"] == 2
    assert reloaded_after_second["status"] == "finished"
    assert reloaded_after_second["current_step_index"] == reloaded_after_second["steps_total"]
    assert reloaded_after_second["finished_tick"] == 2
    assert reloaded_after_second["finished_at_tick"] == 2
    assert reloaded_after_second["finished_at"]
    assert runtime_state_json["current_step_index"] == runtime_state_json["steps_total"]
    assert runtime_state_json["status"] == "finished"
    assert runtime_state_json["finished_tick"] == 2
    assert runtime_state_json["finished_at"]
    assert runtime_state_json["last_step_result"]["step_index"] == 1
    assert executor.calls == ["first", "second"]


def test_exhausted_runtime_state_marks_finished_without_rerun() -> None:
    executor = FakeStepExecutor()
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    runner = TaskRunner(step_executor=executor, task_runtime=runtime)
    task = _task()

    state = runtime.ensure_runtime_state(task)
    state["current_step_index"] = 99
    runtime.save_runtime_state(task, state)

    result = runner.run_task(_task(), current_tick=3)
    reloaded = runtime.load_runtime_state(_task())

    assert result["ok"] is True
    assert result["action"] == "already_finished"
    assert result["status"] == "finished"
    assert reloaded["current_step_index"] == 2
    assert reloaded["status"] == "finished"
    assert reloaded["finished_tick"] == 3
    assert reloaded["finished_at"]
    assert executor.calls == []


def test_failed_step_does_not_advance_and_persists_error() -> None:
    runtime = TaskRuntime(workspace_root=str(TEST_ROOT))
    runner = TaskRunner(step_executor=FailingStepExecutor(), task_runtime=runtime)

    result = runner.run_task(_task(), current_tick=1)
    reloaded = runtime.load_runtime_state(_task())

    assert result["ok"] is False
    assert result["action"] == "step_failed"
    assert result["status"] == "failed"
    assert reloaded["current_step_index"] == 0
    assert reloaded["status"] == "failed"
    assert reloaded["last_error"] == "first failed"
    assert reloaded["last_step_result"]["step_index"] == 0

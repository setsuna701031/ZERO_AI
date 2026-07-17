from pathlib import Path

from core.adaptive import AdaptiveRuntimeResume
from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime


class RecordingExecutor:
    def __init__(self, responses: dict[str, list[dict]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def execute_step(self, **kwargs: object) -> dict:
        step = kwargs["step"]
        assert isinstance(step, dict)
        step_id = str(step["id"])
        self.calls.append(step_id)
        response = self.responses[step_id].pop(0)
        response.setdefault("step_index", int(kwargs["step_index"]))
        return response


def _task(tmp_path: Path, steps: list[dict]) -> dict:
    task_dir = tmp_path / "task"
    return {
        "task_id": "adaptive-task",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": steps,
    }


def test_resume_from_failed_step_does_not_rerun_completed_step(tmp_path: Path) -> None:
    executor = RecordingExecutor({
        "first": [{"ok": True}],
        "second": [{"ok": False, "error": "failed once"}, {"ok": True}],
        "third": [{"ok": True}],
    })
    task = _task(tmp_path, [{"id": "first"}, {"id": "second"}, {"id": "third"}])
    runner = TaskRunner(step_executor=executor, task_runtime=TaskRuntime(workspace_root=str(tmp_path)))
    adaptive = AdaptiveRuntimeResume(max_cycles=8)

    result = adaptive.run(task_runner=runner, task=task)

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["deviation"]["observed"]["error"]["type"] == "execution_authority_denied"
    assert result["deviation"]["observed"]["executed"] is False
    assert executor.calls == []
    state = result["result"]["runtime_state"]
    assert state["status"] == "blocked"
    assert [record["step_index"] for record in state["execution_log"]] == [0, 0, 0]
    assert all(record["result"]["executed"] is False for record in state["execution_log"])
    assert state.get("runtime_execution_capability") is None
    assert state.get("completion_authority") is None
    assert state.get("task_completion_authority") is None
    assert state.get("goal_completion_attestation") is None


def test_adaptive_loop_stops_at_retry_limit(tmp_path: Path) -> None:
    executor = RecordingExecutor({
        "timeout-step": [
            {"ok": False, "error": "tool timeout"},
            {"ok": False, "error": "tool timeout"},
            {"ok": False, "error": "tool timeout"},
        ]
    })
    task = _task(tmp_path, [{"id": "timeout-step"}])
    runner = TaskRunner(step_executor=executor, task_runtime=TaskRuntime(workspace_root=str(tmp_path)))

    result = AdaptiveRuntimeResume(max_cycles=20).run(task_runner=runner, task=task)

    assert result["status"] == "blocked"
    assert result["decision"]["reason"] == "replan_limit_exhausted"
    assert result["deviation"]["observed"]["error"]["type"] == "execution_authority_denied"
    assert result["deviation"]["observed"]["executed"] is False
    assert executor.calls == []
    state = result["result"]["runtime_state"]
    assert state["status"] == "blocked"
    assert all(record["result"]["executed"] is False for record in state["execution_log"])
    assert state.get("runtime_execution_capability") is None
    assert state.get("completion_authority") is None
    assert state.get("task_completion_authority") is None
    assert state.get("goal_completion_attestation") is None

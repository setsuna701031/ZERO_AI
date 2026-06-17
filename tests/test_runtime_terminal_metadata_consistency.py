from pathlib import Path

from core.adaptive import AdaptiveRuntimeResume, DeviationDetector
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime


class SequenceExecutor:
    def __init__(self, responses: dict[str, list[dict]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def execute_step(self, **kwargs: object) -> dict:
        step = kwargs["step"]
        assert isinstance(step, dict)
        step_id = str(step["id"])
        self.calls.append(step_id)
        result = dict(self.responses[step_id].pop(0))
        result.setdefault("step_index", int(kwargs["step_index"]))
        return result


def _task(tmp_path: Path, steps: list[dict], task_id: str = "terminal-consistency") -> dict:
    task_dir = tmp_path / task_id
    return {
        "task_id": task_id,
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": steps,
    }


def _dispatcher_owned_task(
    tmp_path: Path,
    steps: list[dict],
    task_id: str = "terminal-consistency",
) -> dict:
    task = _task(tmp_path, steps, task_id)
    task["package_id"] = f"{task_id}-package"
    task["session_id"] = f"{task_id}-session"
    task["runtime_execution_capability"] = RuntimeDispatcher._execution_capability(task)
    return task


def _current_subgoal_status(state: dict) -> str:
    context = state.get("repair_context", {})
    goal = context.get("engineering_goal_state", {})
    subgoals = goal.get("subgoals", [])
    return str(subgoals[0].get("status") or "") if subgoals else ""


def test_success_with_missing_artifact_is_not_terminal_finished(tmp_path: Path) -> None:
    task = _dispatcher_owned_task(tmp_path, [{"id": "produce", "expected_artifacts": ["report.txt"]}])
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    runner = TaskRunner(
        step_executor=SequenceExecutor({"produce": [{"ok": True, "artifacts": []}]}),
        task_runtime=runtime,
    )
    executed = runner.run_task(task)
    report = DeviationDetector().detect(
        task_id=task["task_id"],
        step=task["steps"][0],
        step_result=executed["last_result"],
    )
    observed = runner.record_terminal_observation(
        task,
        deviation_report=report.to_dict(),
        evidence_persisted=True,
        deviation_step_index=0,
    )

    assert executed["status"] == "needs_observation"
    assert observed["status"] == "needs_resume"
    assert observed["runtime_state"]["current_step_index"] == 0
    assert _current_subgoal_status(observed["runtime_state"]) == "needs_resume"
    assert len(observed["runtime_state"]["execution_log"]) == 1


def test_missing_dispatcher_capability_cannot_reach_terminal_metadata(tmp_path: Path) -> None:
    task = _task(tmp_path, [{"id": "produce", "expected_artifacts": ["report.txt"]}])
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    runner = TaskRunner(
        step_executor=SequenceExecutor({"produce": [{"ok": True, "artifacts": []}]}),
        task_runtime=runtime,
    )

    executed = runner.run_task(task)

    assert executed["status"] == "retrying"
    assert executed["failure_type"] == "execution_authority_denied"
    assert executed["last_result"]["executed"] is False
    assert executed["last_result"]["blocked"] is True
    assert executed["runtime_state"]["status"] == "blocked"


def test_finished_requires_observation_artifact_validation_and_evidence(tmp_path: Path) -> None:
    task = _dispatcher_owned_task(tmp_path, [{"id": "produce", "expected_artifacts": ["report.txt"]}], "valid-finish")
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    runner = TaskRunner(
        step_executor=SequenceExecutor({"produce": [{"ok": True, "artifacts": ["report.txt"]}]}),
        task_runtime=runtime,
    )
    executed = runner.run_task(task)
    report = DeviationDetector().detect(task_id=task["task_id"], step=task["steps"][0], step_result=executed["last_result"])
    not_sealed = runner.record_terminal_observation(
        task,
        deviation_report=report.to_dict(),
        evidence_persisted=False,
        deviation_step_index=0,
    )
    sealed = runner.record_terminal_observation(
        task,
        deviation_report=report.to_dict(),
        evidence_persisted=True,
        deviation_step_index=0,
    )

    assert executed["status"] == "needs_observation"
    assert not_sealed["status"] == "completion_rejected"
    assert sealed["status"] == "completion_rejected"


def test_finished_metadata_can_downgrade_through_runtime_contract(tmp_path: Path) -> None:
    task = _dispatcher_owned_task(tmp_path, [{"id": "produce"}], "downgrade")
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    runner = TaskRunner(step_executor=SequenceExecutor({"produce": [{"ok": True}]}), task_runtime=runtime)

    finished = runner.run_task(task)
    report = {
        "deviation_detected": True,
        "reason": "artifact_missing",
        "recoverable": True,
    }
    downgraded = runner.record_terminal_observation(
        task,
        deviation_report=report,
        evidence_persisted=True,
        deviation_step_index=0,
    )

    assert finished["status"] == "finished"
    assert downgraded["status"] == "needs_resume"
    assert downgraded["runtime_state"]["status"] == "needs_resume"
    assert downgraded["runtime_state"]["last_error"] == "artifact_missing"


def test_contract_violation_blocks_and_cannot_resume(tmp_path: Path) -> None:
    task = _dispatcher_owned_task(tmp_path, [{"id": "contract-step"}], "contract-block")
    executor = SequenceExecutor({
        "contract-step": [{"ok": False, "error": {"type": "contract_violation", "message": "bad contract"}}]
    })
    runner = TaskRunner(step_executor=executor, task_runtime=TaskRuntime(workspace_root=str(tmp_path)))

    result = AdaptiveRuntimeResume(max_cycles=5).run(task_runner=runner, task=task)

    assert result["status"] == "blocked"
    assert result["decision"]["action"] == "block"
    assert result["deviation"]["reason"] == "contract_violation"
    assert executor.calls == ["contract-step"]


def test_resume_preserves_completed_logs_and_reexecutes_deviation_point(tmp_path: Path) -> None:
    task = _dispatcher_owned_task(
        tmp_path,
        [{"id": "first"}, {"id": "produce", "expected_artifacts": ["report.txt"]}],
        "resume-preserves",
    )
    executor = SequenceExecutor({
        "first": [{"ok": True}],
        "produce": [{"ok": True, "artifacts": []}, {"ok": True, "artifacts": ["report.txt"]}],
    })
    runner = TaskRunner(step_executor=executor, task_runtime=TaskRuntime(workspace_root=str(tmp_path)))

    result = AdaptiveRuntimeResume(max_cycles=8).run(task_runner=runner, task=task)
    state = result["result"]["runtime_state"]

    assert result["status"] == "blocked"
    assert executor.calls == ["first", "produce", "produce"]
    assert len(state["execution_log"]) == 3
    assert [record["step_index"] for record in state["execution_log"]] == [0, 1, 1]
    assert len(state["adaptive_evidence_chain"]) >= 5

from pathlib import Path

from core.adaptive import AdaptiveEvidenceChain, AdaptiveRuntimeResume
from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime


class ArtifactExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute_step(self, **kwargs: object) -> dict:
        self.calls += 1
        if self.calls == 1:
            return {"ok": True, "artifacts": []}
        return {"ok": True, "artifacts": ["report.txt"]}


def test_evidence_chain_traces_replan_and_resume(tmp_path: Path) -> None:
    task_dir = tmp_path / "task"
    task = {
        "task_id": "evidence-task",
        "plan_id": "plan-original",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [{"id": "produce", "expected_artifacts": ["report.txt"]}],
    }
    runner = TaskRunner(step_executor=ArtifactExecutor(), task_runtime=TaskRuntime(workspace_root=str(tmp_path)))

    result = AdaptiveRuntimeResume(max_cycles=5).run(task_runner=runner, task=task)
    chain = result["evidence_chain"]
    kinds = [record["kind"] for record in chain]

    assert result["status"] == "blocked"
    assert result["ok"] is False
    assert kinds[:4] == ["original_plan", "deviation", "decision", "revised_plan"]
    assert AdaptiveEvidenceChain().validate(chain)["ok"] is True
    assert chain[1]["payload"]["reason"] == "artifact_missing"
    assert chain[2]["payload"]["resume_from_step_id"] == "produce"
    assert chain[3]["payload"]["original_plan_id"] == "plan-original"

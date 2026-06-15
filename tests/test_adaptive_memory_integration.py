from pathlib import Path

from core.adaptive import AdaptiveRuntimeResume, MemoryAwareReplanner
from core.memory import IssueMemory, MemoryRepository
from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime


class SequenceExecutor:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = responses
        self.calls = 0

    def execute_step(self, **kwargs) -> dict:
        self.calls += 1
        result = dict(self.responses.pop(0))
        result.setdefault("step_index", int(kwargs["step_index"]))
        return result


def _task(tmp_path: Path, *, task_id: str, step: dict) -> dict:
    task_dir = tmp_path / task_id
    return {
        "task_id": task_id,
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [step],
    }


def test_adaptive_resume_injects_context_without_memory_write(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.append(
        IssueMemory(
            "issue-1",
            "report.txt artifact missing",
            "writer omitted report",
            "restore report",
            "adaptive-task",
            ["ev-1"],
            "reported",
        )
    )
    before = repository.storage_path.read_bytes()
    adaptive = AdaptiveRuntimeResume(memory_repository=repository, max_cycles=5)
    runner = TaskRunner(
        step_executor=SequenceExecutor(
            [{"ok": True, "artifacts": []}, {"ok": True, "artifacts": ["report.txt"]}]
        ),
        task_runtime=TaskRuntime(workspace_root=str(tmp_path)),
    )

    result = adaptive.run(
        task_runner=runner,
        task=_task(tmp_path, task_id="adaptive-task", step={"id": "produce", "expected_artifacts": ["report.txt"]}),
    )

    assert result["status"] == "blocked"
    assert isinstance(adaptive.replanner, MemoryAwareReplanner)
    assert adaptive.replanner.last_memory_context.related_issues[0].memory_id == "issue-1"
    assert repository.storage_path.read_bytes() == before


def test_query_failure_does_not_interrupt_transient_retry(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.storage_path.parent.mkdir(parents=True)
    repository.storage_path.write_text("invalid-json\n", encoding="utf-8")
    before = repository.storage_path.read_bytes()
    adaptive = AdaptiveRuntimeResume(memory_repository=repository, max_cycles=5)
    runner = TaskRunner(
        step_executor=SequenceExecutor([{"ok": False, "error": "tool timeout"}, {"ok": True}]),
        task_runtime=TaskRuntime(workspace_root=str(tmp_path)),
    )

    result = adaptive.run(
        task_runner=runner,
        task=_task(tmp_path, task_id="retry-task", step={"id": "retry-step"}),
    )

    assert result["status"] == "blocked"
    assert adaptive.replanner.last_memory_context.warnings
    assert repository.storage_path.read_bytes() == before


def test_contract_violation_still_blocks_in_memory_aware_runtime(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.append(
        IssueMemory("issue-1", "contract issue", "bad contract", "manual review", "contract-task")
    )
    runner = TaskRunner(
        step_executor=SequenceExecutor(
            [{"ok": False, "error": {"type": "contract_violation", "message": "bad contract"}}]
        ),
        task_runtime=TaskRuntime(workspace_root=str(tmp_path)),
    )

    result = AdaptiveRuntimeResume(memory_repository=repository, max_cycles=5).run(
        task_runner=runner,
        task=_task(tmp_path, task_id="contract-task", step={"id": "contract-step"}),
    )

    assert result["status"] == "blocked"
    assert result["decision"]["action"] == "block"
    assert result["deviation"]["reason"] == "contract_violation"

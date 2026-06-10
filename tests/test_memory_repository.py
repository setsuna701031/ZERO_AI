import ast
import json
from pathlib import Path

import pytest

from core.memory import DecisionMemory, MemoryRepository, MemoryType, TaskMemory


def _task(task_id: str = "task-1") -> TaskMemory:
    return TaskMemory(
        task_id=task_id,
        goal="Build memory",
        plan_id="plan-1",
        start_time="2026-06-09T01:00:00Z",
        end_time="2026-06-09T02:00:00Z",
        result="completed",
        evidence_refs=["evidence-1"],
    )


def test_repository_append_query_persist_reload_and_lookup(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.append(_task())
    repository.append(
        DecisionMemory(
            decision_id="decision-1",
            context={"task_id": "task-1"},
            decision="resume",
            reason="approved",
            timestamp="2026-06-09T03:00:00Z",
        )
    )

    assert repository.storage_path == tmp_path / "runtime" / "memory" / "memory.jsonl"
    assert repository.query({"record_id": "task-1"})[0]["goal"] == "Build memory"
    assert len(repository.list_by_type(MemoryType.DECISION)) == 1
    assert len(repository.list_by_task("task-1")) == 1
    assert repository.list_recent(1)[0]["decision_id"] == "decision-1"
    assert len(MemoryRepository(tmp_path).list_by_type("task")) == 1


def test_repository_is_append_only(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.append(_task())
    repository.append(_task())

    lines = repository.storage_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["task_id"] == "task-1" for line in lines)


def test_repository_rejects_contract_violation_without_repair(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)

    with pytest.raises(ValueError, match="memory_requires_record_id"):
        repository.append({"memory_type": "task", "timestamp": "now"})

    assert not repository.storage_path.exists()


def test_memory_layer_has_no_execution_system_imports() -> None:
    memory_root = Path(__file__).resolve().parents[1] / "core" / "memory"
    new_modules = {
        "memory_contract.py",
        "decision_memory.py",
        "issue_memory.py",
        "engineering_memory.py",
        "memory_repository.py",
        "memory_query.py",
    }
    imports: set[str] = set()
    for path in memory_root.iterdir():
        if path.name not in new_modules:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

    assert not any(
        name.startswith(("core.runtime", "core.adaptive", "core.agent", "core.tasks"))
        for name in imports
    )

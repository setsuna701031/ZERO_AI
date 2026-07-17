import copy
from pathlib import Path

from core.memory import MemoryRepository, TaskMemory
from core.planning.memory_aware_planner import MemoryAwarePlanner
from core.planning.memory_context import MemoryContextBuilder


class RecordingPlanner:
    def __init__(self) -> None:
        self.context = None
        self.plan_result = {"ok": True, "steps": [{"type": "inspect"}]}

    def plan(self, context=None, user_input="", route=None, **kwargs):
        self.context = copy.deepcopy(context)
        return copy.deepcopy(self.plan_result)


def test_thin_adapter_injects_context_without_modifying_plan_or_input(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.append(
        TaskMemory("task-1", "Inspect history", "plan-1", "2026-06-09T01:00:00Z", None, "done")
    )
    planner = RecordingPlanner()
    adapter = MemoryAwarePlanner(planner, MemoryContextBuilder(repository))
    input_context = {"task_id": "task-1", "owner": "planner"}
    before_plan = copy.deepcopy(planner.plan_result)

    result = adapter.plan(context=input_context, user_input="Inspect history")

    assert planner.context["memory_context"]["related_tasks"][0]["memory_id"] == "task-1"
    assert input_context == {"task_id": "task-1", "owner": "planner"}
    assert result == before_plan


def test_thin_adapter_without_repository_keeps_planner_operational() -> None:
    planner = RecordingPlanner()

    result = MemoryAwarePlanner(planner).plan(user_input="ordinary planning request")

    assert result["ok"] is True
    assert planner.context["memory_context"]["related_tasks"] == []


def test_query_failure_injects_warning_and_does_not_crash(tmp_path: Path) -> None:
    repository = MemoryRepository(tmp_path)
    repository.storage_path.parent.mkdir(parents=True)
    repository.storage_path.write_text("not-json\n", encoding="utf-8")
    planner = RecordingPlanner()

    result = MemoryAwarePlanner(planner, MemoryContextBuilder(repository)).plan(
        context={"task_id": "task-1"},
        user_input="plan",
    )

    assert result["ok"] is True
    assert planner.context["memory_context"]["warnings"]

import copy
import json
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.memory import MemoryRepository, TaskMemory
from core.planning.planner import Planner
from core.system.llm_planner import LLMPlanner


class CapturingLLM:
    def __init__(self) -> None:
        self.prompt = ""

    def generate_general(self, prompt: str):
        self.prompt = prompt
        return {"response": '{"intent":"respond","final_answer":"ok","steps":[]}'}


class RepositoryAwarePlanner:
    def __init__(self) -> None:
        self.repository = None

    def set_memory_repository(self, repository) -> None:
        self.repository = repository

    def plan(self, context=None, user_input="", route=None, **kwargs):
        return {"ok": True, "steps": []}


def _repository(tmp_path: Path) -> MemoryRepository:
    repository = MemoryRepository(tmp_path)
    repository.append(
        TaskMemory("task-1", "Explain architecture", "plan-1", "2026-06-09T01:00:00Z", None, "done", ["ev-1"])
    )
    return repository


def test_existing_planner_api_remains_compatible_and_memory_does_not_change_plan(tmp_path: Path) -> None:
    plain = Planner()
    aware = Planner(memory_repository=_repository(tmp_path))
    request = "write hello to workspace/shared/memory_aware.txt"

    plain_result = plain.plan(context={"task_id": "task-1"}, user_input=request)
    aware_result = aware.plan(context={"task_id": "task-1"}, user_input=request)
    explicit_result = plain.plan(
        context={"task_id": "task-1"},
        user_input=request,
        memory_context={"task_id": "task-1", "related_tasks": [{"memory_id": "manual"}]},
    )

    assert aware_result == plain_result
    assert explicit_result == plain_result
    assert plain.run(user_input=request) == plain.plan(user_input=request)


def test_llm_planner_receives_memory_context_as_planner_input(tmp_path: Path) -> None:
    llm = CapturingLLM()
    planner = LLMPlanner(llm, memory_repository=_repository(tmp_path))

    result = planner.plan(context={"task_id": "task-1"}, user_input="Explain architecture choices")
    prompt_input = json.loads(llm.prompt.split("Input:\n", 1)[1])

    assert result["ok"] is True
    assert prompt_input["memory_context"]["related_tasks"][0]["memory_id"] == "task-1"


def test_agent_loop_only_passes_repository_configuration_to_planner(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    planner = RepositoryAwarePlanner()

    AgentLoop(planner=planner, memory_repository=repository)

    assert planner.repository is repository

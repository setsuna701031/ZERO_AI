import ast
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.goals import GoalRepository
from core.planning.planner import Planner


class RepositoryAwarePlanner:
    def __init__(self) -> None:
        self.repository = None

    def set_goal_repository(self, repository) -> None:
        self.repository = repository


def test_no_goal_repository_keeps_existing_planner_and_agent_loop_working() -> None:
    planner = Planner()
    result = planner.plan(user_input="")
    loop = AgentLoop(planner=planner)

    assert result["steps"] == []
    assert loop.goal_repository is None


def test_agent_loop_only_passes_goal_repository_configuration(tmp_path: Path) -> None:
    repository = GoalRepository(tmp_path)
    planner = RepositoryAwarePlanner()

    loop = AgentLoop(planner=planner, goal_repository=repository)

    assert loop.goal_repository is repository
    assert planner.repository is repository
    assert not repository.storage_path.exists()


def test_goal_layer_has_no_runtime_adaptive_memory_or_agent_imports() -> None:
    goals_root = Path(__file__).resolve().parents[1] / "core" / "goals"
    imports: set[str] = set()
    for path in goals_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

    assert not any(
        name.startswith(("core.runtime", "core.adaptive", "core.memory", "core.agent"))
        for name in imports
    )

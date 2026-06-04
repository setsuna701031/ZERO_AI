from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.engineering_stack_contract import ALLOWED, FORBIDDEN, OWNERS, QUESTION_OWNERS


REPO_ROOT = Path(__file__).resolve().parents[1]

MODULE_FILES = {
    "core.tasks.engineering_goal_portfolio": REPO_ROOT / "core/tasks/engineering_goal_portfolio.py",
    "core.tasks.adaptive_planning_evaluator": REPO_ROOT / "core/tasks/adaptive_planning_evaluator.py",
    "core.tasks.engineering_planning_loop": REPO_ROOT / "core/tasks/engineering_planning_loop.py",
    "core.tasks.engineering_goal_lifecycle": REPO_ROOT / "core/tasks/engineering_goal_lifecycle.py",
    "core.tasks.goal_continuation_coordinator": REPO_ROOT / "core/tasks/goal_continuation_coordinator.py",
    "core.tasks.engineering_task_runner": REPO_ROOT / "core/tasks/engineering_task_runner.py",
    "core.tasks.engineering_memory_store": REPO_ROOT / "core/tasks/engineering_memory_store.py",
    "core.agent.agent_loop": REPO_ROOT / "core/agent/agent_loop.py",
}


def _tree(module_name: str) -> ast.Module:
    return ast.parse(MODULE_FILES[module_name].read_text(encoding="utf-8"))


def _imported_symbols(tree: ast.AST) -> set[str]:
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                symbols.add(alias.name)
                symbols.add(alias.asname or alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            symbols.add(module)
            for alias in node.names:
                symbols.add(alias.name)
                symbols.add(alias.asname or alias.name)
                symbols.add(f"{module}.{alias.name}")
    return symbols


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _name(node.func)
    return ""


def _called_symbols(tree: ast.AST) -> set[str]:
    return {_name(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}


def _string_literals(tree: ast.AST) -> set[str]:
    return {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def _function_node(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function not found: {name}")


def test_architecture_contract_answers_ownership_questions() -> None:
    assert QUESTION_OWNERS == {
        "Who owns multi-goal selection?": "core.tasks.engineering_goal_portfolio.EngineeringGoalPortfolio",
        "Who owns planning?": "core.tasks.engineering_planning_loop.EngineeringPlanningLoop",
        "Who owns lifecycle?": "core.tasks.engineering_goal_lifecycle.EngineeringGoalLifecycle",
        "Who owns evaluation?": "core.tasks.adaptive_planning_evaluator.AdaptivePlanningEvaluator",
        "Who owns continuation?": "core.tasks.goal_continuation_coordinator.GoalContinuationCoordinator",
        "Who owns execution?": "core.tasks.engineering_task_runner",
        "Who owns memory?": "core.tasks.engineering_memory_store.EngineeringMemoryStore",
    }
    assert set(OWNERS) == {"portfolio", "planning", "lifecycle", "evaluation", "continuation", "execution", "memory", "dispatch"}
    assert set(ALLOWED) == set(FORBIDDEN) == set(MODULE_FILES)
    assert len(set(OWNERS.values())) == len(OWNERS)


def test_stack_boundary_includes_portfolio_contract() -> None:
    assert OWNERS["portfolio"] == "core.tasks.engineering_goal_portfolio.EngineeringGoalPortfolio"
    assert "core.tasks.engineering_goal_portfolio" in ALLOWED
    assert "core.tasks.engineering_goal_portfolio" in FORBIDDEN
    assert any("selection across multiple engineering goals" in item for item in ALLOWED["core.tasks.engineering_goal_portfolio"])
    assert any("Execute work packages" in item for item in FORBIDDEN["core.tasks.engineering_goal_portfolio"])


def test_engineering_goal_portfolio_selects_only() -> None:
    tree = _tree("core.tasks.engineering_goal_portfolio")
    imports = _imported_symbols(tree)
    calls = _called_symbols(tree)

    forbidden_imports = {
        "Planner",
        "core.planning.planner",
        "EngineeringTaskRunner",
        "core.tasks.engineering_task_runner",
        "run_engineering_task",
        "EngineeringMemoryStore",
        "core.tasks.engineering_memory_store",
        "EngineeringGoalLifecycle",
        "core.tasks.engineering_goal_lifecycle",
        "WorkPackageScheduler",
        "core.tasks.work_package_scheduler",
        "AgentLoop",
        "core.agent.agent_loop",
    }
    assert imports.isdisjoint(forbidden_imports)
    assert "run_engineering_task" not in calls
    assert "submit_work_package" not in calls
    assert not any(call.endswith(".submit") for call in calls)
    assert "save_record" not in calls
    assert "load_relevant_memory" not in calls
    assert "EngineeringGoalLifecycle" not in calls
    assert "Planner" not in calls
    assert not any(call.endswith(".plan") for call in calls)


def test_adaptive_planning_evaluator_decides_only() -> None:
    tree = _tree("core.tasks.adaptive_planning_evaluator")
    imports = _imported_symbols(tree)
    calls = _called_symbols(tree)

    forbidden_imports = {
        "Planner",
        "core.planning.planner",
        "EngineeringPlanningLoop",
        "core.tasks.engineering_planning_loop",
        "GoalContinuationCoordinator",
        "core.tasks.goal_continuation_coordinator",
        "EngineeringTaskRunner",
        "core.tasks.engineering_task_runner",
        "run_engineering_task",
        "EngineeringMemoryStore",
        "core.tasks.engineering_memory_store",
        "EngineeringGoalLifecycle",
        "core.tasks.engineering_goal_lifecycle",
        "WorkPackageScheduler",
        "core.tasks.work_package_scheduler",
        "AgentLoop",
        "core.agent.agent_loop",
    }
    assert imports.isdisjoint(forbidden_imports)
    assert "run_engineering_task" not in calls
    assert "EngineeringMemoryStore" not in calls
    assert "EngineeringGoalLifecycle" not in calls
    assert "Planner" not in calls
    assert not any(call.endswith(".plan") for call in calls)
    assert "submit_work_package" not in calls
    assert not any(call.endswith(".submit") for call in calls)


def test_planning_loop_does_not_execute_or_own_memory_or_lifecycle_state() -> None:
    tree = _tree("core.tasks.engineering_planning_loop")
    imports = _imported_symbols(tree)
    calls = _called_symbols(tree)

    assert "WorkPackageScheduler" not in imports
    assert "core.tasks.work_package_scheduler" not in imports
    assert "run_engineering_task" not in imports
    assert "run_engineering_task" not in calls
    assert "submit_work_package" not in calls
    assert not any(call.endswith(".submit") for call in calls)

    assert "save_record" not in calls
    assert not any(call.endswith(".save_record") for call in calls)
    assert "_write_store" not in calls

    assert "_write_json" not in calls
    assert ".engineering_goal_state.json" not in _string_literals(tree)


def test_goal_continuation_coordinator_does_not_plan_replan_or_own_memory() -> None:
    tree = _tree("core.tasks.goal_continuation_coordinator")
    imports = _imported_symbols(tree)
    calls = _called_symbols(tree)

    assert "Planner" not in imports
    assert "core.planning.planner" not in imports
    assert "EngineeringPlanningLoop" not in imports
    assert "core.tasks.engineering_planning_loop" not in imports
    assert "EngineeringMemoryStore" not in imports
    assert "core.tasks.engineering_memory_store" not in imports

    assert "Planner" not in calls
    assert "plan" not in calls
    assert not any(call.endswith(".plan") for call in calls)
    assert not any("replan" in call.lower() for call in calls)
    assert "load_relevant_memory" not in calls
    assert "save_record" not in calls

    assert "WorkPackageScheduler" not in imports
    assert "submit_work_package" not in calls
    assert not any(call.endswith(".submit") for call in calls)


def test_engineering_task_runner_does_not_own_planning_replanning_or_lifecycle_state() -> None:
    tree = _tree("core.tasks.engineering_task_runner")
    imports = _imported_symbols(tree)
    calls = _called_symbols(tree)

    assert "EngineeringPlanningLoop" not in imports
    assert "GoalContinuationCoordinator" not in imports
    assert "core.tasks.engineering_planning_loop" not in imports
    assert "core.tasks.goal_continuation_coordinator" not in imports

    assert "Planner.plan" not in calls
    assert not any(call.endswith(".plan") for call in calls)
    assert "EngineeringPlanningLoop" not in calls
    assert "GoalContinuationCoordinator" not in calls
    assert "continue_engineering_goal" not in calls

    literals = _string_literals(tree)
    assert ".engineering_goal_state.json" not in literals
    assert "zero.engineering_task.goal_state.v1" not in literals


def test_engineering_memory_store_does_not_execute_plan_or_continue_tasks() -> None:
    tree = _tree("core.tasks.engineering_memory_store")
    imports = _imported_symbols(tree)
    calls = _called_symbols(tree)

    forbidden_imports = {
        "Planner",
        "core.planning.planner",
        "EngineeringPlanningLoop",
        "core.tasks.engineering_planning_loop",
        "GoalContinuationCoordinator",
        "core.tasks.goal_continuation_coordinator",
        "EngineeringTaskRunner",
        "core.tasks.engineering_task_runner",
        "WorkPackageScheduler",
        "core.tasks.work_package_scheduler",
        "EngineeringGoalLifecycle",
        "core.tasks.engineering_goal_lifecycle",
    }
    assert imports.isdisjoint(forbidden_imports)
    assert "run_engineering_task" not in calls
    assert "continue_engineering_goal" not in calls
    assert "Planner" not in calls
    assert not any(call.endswith(".plan") for call in calls)
    assert "submit_work_package" not in calls
    assert not any(call.endswith(".submit") for call in calls)


def test_agent_loop_engineering_route_remains_dispatch_only() -> None:
    tree = _tree("core.agent.agent_loop")
    method = _function_node(tree, "_try_handle_engineering_task_route")
    method_calls = _called_symbols(method)
    method_imports = _imported_symbols(method)

    assert method_imports == {
        "core.tasks.engineering_task_runner",
        "run_engineering_task",
        "core.tasks.engineering_task_runner.run_engineering_task",
    }
    assert "run_engineering_task" in method_calls
    assert "Planner" not in method_calls
    assert "EngineeringPlanningLoop" not in method_calls
    assert "GoalContinuationCoordinator" not in method_calls
    assert "EngineeringGoalLifecycle" not in method_calls
    assert "EngineeringMemoryStore" not in method_calls
    assert "AdaptivePlanningEvaluator" not in method_calls
    assert "WorkPackageScheduler" not in method_calls
    assert "submit_work_package" not in method_calls
    assert not any(call.endswith(".submit") for call in method_calls)


def test_agent_loop_imports_no_engineering_state_owners() -> None:
    tree = _tree("core.agent.agent_loop")
    imports = _imported_symbols(tree)

    assert "EngineeringGoalLifecycle" not in imports
    assert "EngineeringMemoryStore" not in imports
    assert "GoalContinuationCoordinator" not in imports
    assert "EngineeringPlanningLoop" not in imports
    assert "AdaptivePlanningEvaluator" not in imports

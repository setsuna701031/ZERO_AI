from __future__ import annotations

import ast
import json
from pathlib import Path

from cli import goal_cli


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_FILE = REPO_ROOT / "core/tasks/engineering_goal_runner.py"


def _imported_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
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


def _called_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))

    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    return {name(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}


def test_goal_runner_is_repository_to_runtime_bridge_only() -> None:
    imports = _imported_symbols(RUNNER_FILE)
    calls = _called_symbols(RUNNER_FILE)

    assert "EngineeringGoalRepository" in imports
    assert "EngineeringRuntimeOrchestrator" in imports
    forbidden_imports = {
        "EngineeringGoalScheduler",
        "core.tasks.engineering_goal_scheduler",
        "EngineeringTaskRunner",
        "core.tasks.engineering_task_runner",
        "run_engineering_task",
        "WorkPackageScheduler",
        "core.tasks.work_package_scheduler",
        "AgentLoop",
        "core.agent.agent_loop",
    }
    assert imports.isdisjoint(forbidden_imports)
    assert "run_engineering_task" not in calls
    assert "submit_work_package" not in calls
    assert not any(call.endswith(".submit") for call in calls)
    assert "save_goal" not in calls
    assert "update_goal" not in calls


def test_goal_cli_run_command_invokes_runner(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ZERO_GOAL_STORE", str(tmp_path / "goals.json"))
    assert goal_cli.try_handle_goal_command(["goal", "add", "Build demo system"], repo_root=REPO_ROOT) is True
    created = json.loads(capsys.readouterr().out)

    assert goal_cli.try_handle_goal_command(
        ["goal", "run", created["goal"]["goal_id"]],
        repo_root=REPO_ROOT,
    ) is True
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["runner_result"]["action"] == "run_goal"
    assert payload["runner_result"]["runtime_request"]["goals"][0]["goal_id"] == created["goal"]["goal_id"]
    assert payload["runner_result"]["runtime_request"]["runtime_entrypoint"].endswith("EngineeringRuntimeOrchestrator.run")
    assert payload["runner_result"]["runtime_result"]["mode"] == "engineering_runtime_orchestrator"
    assert payload["runner_result"]["runtime_result"]["state"] != "complete"


def test_goal_cli_run_next_command_invokes_runner(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("ZERO_GOAL_STORE", str(tmp_path / "goals.json"))
    assert goal_cli.try_handle_goal_command(["goal", "add", "Build demo system"], repo_root=REPO_ROOT) is True
    capsys.readouterr()

    assert goal_cli.try_handle_goal_command(["goal", "run-next"], repo_root=REPO_ROOT) is True
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["runner_result"]["action"] == "run_next_goal"
    assert payload["runner_result"]["runtime_request"]["goals"]
    assert payload["runner_result"]["execution_path"]["runtime_orchestrator_owns_runtime_loop"] is True
    assert payload["runner_result"]["runtime_result"]["state"] != "complete"

from __future__ import annotations

import ast
import json
from pathlib import Path

from cli import goal_cli


REPO_ROOT = Path(__file__).resolve().parents[1]
GOAL_CLI_FILE = REPO_ROOT / "cli/goal_cli.py"


def _run_goal_cli(argv: list[str], tmp_path: Path, monkeypatch, capsys) -> dict:
    monkeypatch.setenv("ZERO_WORKSPACE", str(tmp_path))
    handled = goal_cli.try_handle_goal_command(argv, repo_root=REPO_ROOT)
    assert handled is True
    return json.loads(capsys.readouterr().out)


def _store_path(tmp_path: Path) -> Path:
    return tmp_path / "engineering_goals.json"


def _write_store(tmp_path: Path, payload: dict) -> None:
    _store_path(tmp_path).write_text(json.dumps(payload), encoding="utf-8")


class SpyScheduler:
    calls: list[tuple[str, str | None, list[dict]]]

    def __init__(self) -> None:
        self.calls = []

    def schedule_next_goal(self, goals):
        self.calls.append(("schedule_next_goal", None, list(goals)))
        return {
            "ok": True,
            "scheduler_decision": {"action": "schedule_next_goal", "selected_goal_id": "goal_1"},
            "execution_path": {"direct_execution": False, "new_execution_path": False},
        }

    def pause_goal(self, goals, goal_id):
        self.calls.append(("pause_goal", goal_id, list(goals)))
        return {"ok": True, "goals": [{**goals[0], "status": "paused"}], "scheduler_decision": {"action": "pause_goal"}}

    def resume_goal(self, goals, goal_id):
        self.calls.append(("resume_goal", goal_id, list(goals)))
        return {"ok": True, "goals": [{**goals[0], "status": "pending"}], "scheduler_decision": {"action": "resume_goal"}}

    def cancel_goal(self, goals, goal_id):
        self.calls.append(("cancel_goal", goal_id, list(goals)))
        return {"ok": True, "goals": [{**goals[0], "status": "cancelled"}], "scheduler_decision": {"action": "cancel_goal"}}

    def defer_goal(self, goals, goal_id):
        self.calls.append(("defer_goal", goal_id, list(goals)))
        return {"ok": True, "goals": [{**goals[0], "status": "deferred"}], "scheduler_decision": {"action": "defer_goal"}}


def _goal(goal_id: str, summary: str = "Build console") -> dict:
    return {
        "goal_id": goal_id,
        "priority": 0.0,
        "status": "pending",
        "created_at": 1.0,
        "updated_at": 1.0,
        "payload": {"goal": summary, "goal_id": goal_id},
        "summary": summary,
    }


def test_goal_add_creates_listable_goal_record(tmp_path, monkeypatch, capsys) -> None:
    add_result = _run_goal_cli(["goal", "add", "Build the control console"], tmp_path, monkeypatch, capsys)

    assert add_result["ok"] is True
    goal_id = add_result["goal"]["goal_id"]
    assert add_result["goal"]["summary"] == "Build the control console"

    list_result = _run_goal_cli(["goal", "list"], tmp_path, monkeypatch, capsys)

    assert list_result["goals"] == [
        {
            "goal_id": goal_id,
            "priority": 0.0,
            "status": "pending",
            "summary": "Build the control console",
        }
    ]


def test_goal_list_prints_deterministic_goal_records(tmp_path, monkeypatch, capsys) -> None:
    _write_store(
        tmp_path,
        {
            "schema": goal_cli.GOAL_CLI_SCHEMA,
            "goals": [
                {**_goal("b"), "priority": 1, "created_at": 2, "summary": "Second"},
                {**_goal("a"), "priority": 2, "created_at": 3, "summary": "First"},
            ],
            "dependencies": [],
        },
    )

    first = _run_goal_cli(["goal", "list"], tmp_path, monkeypatch, capsys)
    second = _run_goal_cli(["goal", "list"], tmp_path, monkeypatch, capsys)

    assert first == second
    assert [item["goal_id"] for item in first["goals"]] == ["a", "b"]


def test_goal_run_next_routes_through_scheduler(tmp_path, monkeypatch, capsys) -> None:
    _write_store(tmp_path, {"schema": goal_cli.GOAL_CLI_SCHEMA, "goals": [_goal("goal_1")], "dependencies": []})
    spy = SpyScheduler()
    monkeypatch.setattr(goal_cli, "EngineeringGoalScheduler", lambda: spy)

    result = _run_goal_cli(["goal", "run-next"], tmp_path, monkeypatch, capsys)

    assert result["ok"] is False
    assert result.get("completed") is not True
    assert result.get("finished") is not True
    assert spy.calls
    assert all(call[0:2] == ("schedule_next_goal", None) for call in spy.calls)
    scheduled_goal = spy.calls[0][2][0]
    assert scheduled_goal["goal_id"] == "goal_1"
    assert scheduled_goal["session_id"]
    assert scheduled_goal["runtime_session_id"]
    assert scheduled_goal["goal_lineage"]["goal_id"] == "goal_1"


def test_goal_state_commands_route_through_scheduler(tmp_path, monkeypatch, capsys) -> None:
    for command, expected_call, expected_status in [
        ("pause", "pause_goal", "paused"),
        ("resume", "resume_goal", "pending"),
        ("cancel", "cancel_goal", "cancelled"),
        ("defer", "defer_goal", "deferred"),
    ]:
        _write_store(tmp_path, {"schema": goal_cli.GOAL_CLI_SCHEMA, "goals": [_goal("goal_1")], "dependencies": []})
        spy = SpyScheduler()
        monkeypatch.setattr(goal_cli, "EngineeringGoalScheduler", lambda: spy)

        result = _run_goal_cli(["goal", command, "goal_1"], tmp_path, monkeypatch, capsys)

        assert result["ok"] is True
        assert spy.calls == [(expected_call, "goal_1", [_goal("goal_1")])]
        stored = json.loads(_store_path(tmp_path).read_text(encoding="utf-8"))
        assert stored["goals"][0]["status"] == expected_status


def test_goal_deps_reads_dependency_graph(tmp_path, monkeypatch, capsys) -> None:
    _write_store(
        tmp_path,
        {
            "schema": goal_cli.GOAL_CLI_SCHEMA,
            "goals": [
                {**_goal("build"), "status": "completed"},
                _goal("ship"),
            ],
            "dependencies": [
                {"goal_id": "build"},
                {"goal_id": "ship", "prerequisite_goal_ids": ["build"]},
            ],
        },
    )

    result = _run_goal_cli(["goal", "deps", "ship"], tmp_path, monkeypatch, capsys)

    assert result["dependency_status"]["ready"] is True
    assert result["dependency_graph"]["records"][1]["goal_id"] == "ship"


def test_goal_cli_does_not_import_task_runner_or_call_execution_paths() -> None:
    tree = ast.parse(GOAL_CLI_FILE.read_text(encoding="utf-8"))
    imports = set()
    calls = set()
    literals = set()

    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            calls.add(name(node.func))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.add(node.value)

    forbidden_imports = {
        "EngineeringTaskRunner",
        "core.tasks.engineering_task_runner",
        "run_engineering_task",
        "WorkPackageScheduler",
    }
    assert imports.isdisjoint(forbidden_imports)
    assert "run_engineering_task" not in calls
    assert "submit_work_package" not in calls
    assert not any(call.endswith(".submit") for call in calls)
    assert not any("AER" in literal for literal in literals)

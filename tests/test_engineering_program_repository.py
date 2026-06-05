from __future__ import annotations

import ast
import json
from pathlib import Path

from core.tasks.engineering_program_repository import (
    ENGINEERING_PROGRAM_REPOSITORY_SCHEMA,
    EngineeringProgram,
    EngineeringProgramRepository,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PROGRAM_FILE = REPO_ROOT / "core/tasks/engineering_program_repository.py"


def test_create_load_and_list_program(tmp_path) -> None:
    repository = EngineeringProgramRepository(tmp_path)

    created = repository.create_program({"program_id": "program_1", "name": "Engineering Program v1", "description": "Layered work"})
    loaded = repository.load_program("program_1")
    listed = repository.list_programs()

    assert created["program_id"] == "program_1"
    assert created["name"] == "Engineering Program v1"
    assert created["description"] == "Layered work"
    assert created["portfolio_ids"] == []
    assert loaded == created
    assert listed == [created]
    assert repository.storage_path == tmp_path / "runtime" / "programs" / "programs.json"


def test_program_portfolio_refs_are_added_removed_and_persisted(tmp_path) -> None:
    repository = EngineeringProgramRepository(tmp_path)
    repository.create_program("Platform program")

    program_id = repository.list_programs()[0]["program_id"]
    added = repository.add_portfolio(program_id, "portfolio_1")
    duplicate = repository.add_portfolio(program_id, "portfolio_1")
    repository.add_portfolio(program_id, "portfolio_2")
    refs_after_restart = EngineeringProgramRepository(tmp_path).load_program(program_id)["portfolio_ids"]
    removed = EngineeringProgramRepository(tmp_path).remove_portfolio(program_id, "portfolio_1")

    assert added["portfolio_ids"] == ["portfolio_1"]
    assert duplicate["portfolio_ids"] == ["portfolio_1"]
    assert refs_after_restart == ["portfolio_1", "portfolio_2"]
    assert removed["portfolio_ids"] == ["portfolio_2"]


def test_program_dataclass_normalizes_to_program_fields_only() -> None:
    program = EngineeringProgram.from_mapping(
        {
            "program_id": "program_1",
            "name": "Normalize refs",
            "portfolio_ids": ["portfolio_1", "portfolio_1", "", "portfolio_2"],
            "goal_ids": ["goal_1"],
            "runtime_task_chain": ["task_1"],
        }
    )

    record = program.as_dict()

    assert record == {
        "program_id": "program_1",
        "name": "Normalize refs",
        "description": "",
        "portfolio_ids": ["portfolio_1", "portfolio_2"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }
    assert "goal_ids" not in record
    assert "runtime_task_chain" not in record


def test_program_repository_file_schema_and_record_shape(tmp_path) -> None:
    repository = EngineeringProgramRepository(tmp_path)
    repository.create_program({"program_id": "program_1", "name": "Schema proof"})

    payload = json.loads(repository.storage_path.read_text(encoding="utf-8"))
    record = payload["programs"][0]

    assert payload["schema"] == ENGINEERING_PROGRAM_REPOSITORY_SCHEMA
    assert set(record) == {"program_id", "name", "description", "portfolio_ids", "created_at", "updated_at"}


def test_program_repository_does_not_import_goal_or_runtime_owners() -> None:
    tree = ast.parse(PROGRAM_FILE.read_text(encoding="utf-8"))
    imports: set[str] = set()
    calls: set[str] = set()

    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.Call):
            calls.add(name(node.func))

    forbidden = {
        "EngineeringGoalRepository",
        "EngineeringGoalRunner",
        "EngineeringGoalLoop",
        "EngineeringRuntimeOrchestrator",
        "EngineeringGoalScheduler",
        "EngineeringAdaptivePlanner",
        "run_engineering_task",
        "core.tasks.engineering_goal_repository",
        "core.tasks.engineering_goal_runner",
        "core.tasks.engineering_goal_loop",
        "core.tasks.engineering_runtime_orchestrator",
        "core.tasks.engineering_goal_scheduler",
        "core.tasks.engineering_adaptive_planner",
        "core.runtime",
    }
    assert imports.isdisjoint(forbidden)
    assert "run_goal" not in calls
    assert "run_until_terminal" not in calls
    assert "schedule_next_goal" not in calls

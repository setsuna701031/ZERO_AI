from __future__ import annotations

import json

import pytest

from core.tasks.engineering_goal_repository import (
    ENGINEERING_GOAL_RECORD_SCHEMA,
    ENGINEERING_GOAL_REPOSITORY_SCHEMA,
    EngineeringGoalRepository,
)


def test_repository_saves_and_loads_goal(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)

    goal = repository.save_goal({"summary": "Persist engineering goal"})
    loaded = repository.load_goal(goal["goal_id"])

    assert goal["schema"] == ENGINEERING_GOAL_RECORD_SCHEMA
    assert loaded == goal
    assert goal["summary"] == "Persist engineering goal"
    assert goal["status"] == "pending"
    assert goal["payload"]["task_type"] == "engineering_task"
    assert (tmp_path / "runtime" / "goals" / "goals.json").is_file()


def test_repository_lists_goals_deterministically(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)

    low = repository.save_goal({"goal_id": "low", "summary": "Low", "priority": 1, "created_at": 2})
    high = repository.save_goal({"goal_id": "high", "summary": "High", "priority": 10, "created_at": 3})
    older = repository.save_goal({"goal_id": "older", "summary": "Older", "priority": 1, "created_at": 1})

    assert [goal["goal_id"] for goal in repository.list_goals()] == ["high", "older", "low"]
    assert EngineeringGoalRepository(tmp_path).list_goals() == [high, older, low]


def test_repository_updates_goal_without_changing_created_at(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"goal_id": "goal_1", "summary": "Initial", "created_at": 1})

    updated = repository.update_goal(
        "goal_1",
        {
            "summary": "Updated",
            "status": "blocked",
            "created_at": 999,
            "payload": {"extra": True},
            "metadata": {"owner": "test"},
        },
    )

    assert updated["goal_id"] == "goal_1"
    assert updated["summary"] == "Updated"
    assert updated["status"] == "blocked"
    assert updated["created_at"] == goal["created_at"]
    assert updated["updated_at"] >= goal["updated_at"]
    assert updated["payload"]["extra"] is True
    assert updated["payload"]["goal_id"] == "goal_1"
    assert updated["metadata"] == {"owner": "test"}


def test_repository_persists_across_instances(tmp_path) -> None:
    first = EngineeringGoalRepository(tmp_path)
    goal = first.save_goal({"goal_id": "restart_goal", "summary": "Survive restart"})

    second = EngineeringGoalRepository(tmp_path)

    assert second.load_goal("restart_goal") == goal
    assert second.list_goals()[0]["goal_id"] == "restart_goal"


def test_repository_rejects_duplicate_goal_id(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "dupe", "summary": "One"})

    with pytest.raises(ValueError):
        repository.save_goal({"goal_id": "dupe", "summary": "Two"})


def test_repository_generated_goal_ids_are_unique_for_repeated_summary(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)

    first = repository.save_goal({"summary": "Build demo system"})
    second = repository.save_goal({"summary": "Build demo system"})

    assert first["goal_id"] != second["goal_id"]
    assert first["summary"] == second["summary"] == "Build demo system"


def test_repository_writes_json_payload_schema(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    repository.save_goal({"goal_id": "goal_1", "summary": "Schema"})

    payload = json.loads((tmp_path / "runtime" / "goals" / "goals.json").read_text(encoding="utf-8"))

    assert payload["schema"] == ENGINEERING_GOAL_REPOSITORY_SCHEMA
    assert payload["goals"][0]["goal_id"] == "goal_1"

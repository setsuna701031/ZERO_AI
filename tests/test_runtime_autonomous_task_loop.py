from __future__ import annotations

from core.runtime.runtime_autonomous_task_loop import (
    RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA,
    RuntimeAutonomousTaskLoop,
    RuntimeAutonomousTaskQueue,
)


def _success_result() -> dict:
    return {
        "ok": True,
        "repair_loop_status": "completed",
        "operator_result": {
            "controlled_mutation_result": {
                "ok": True,
                "mutation_completed": True,
                "validation_passed": True,
            },
        },
    }


def _failed_result() -> dict:
    return {
        "ok": False,
        "denial_reason": "forced_failure",
        "operator_result": {
            "controlled_mutation_result": {
                "ok": False,
                "mutation_completed": False,
                "validation_passed": False,
            },
        },
    }


def test_queue_adds_tasks_with_stable_shape() -> None:
    queue = RuntimeAutonomousTaskQueue()
    result = queue.add_task("update zero_probe.txt with queued data")

    assert result["schema"] == RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA
    assert result["ok"] is True
    assert result["queue_status"] == "queued"
    assert result["queue_depth"] == 1
    assert result["task"]["status"] == "queued"
    assert result["task"]["goal"] == "update zero_probe.txt with queued data"


def test_queue_rejects_empty_task_goal() -> None:
    queue = RuntimeAutonomousTaskQueue()
    result = queue.add_task("")

    assert result["ok"] is False
    assert result["queue_status"] == "denied"
    assert result["denial_reason"] == "task_goal_required"


def test_autonomous_loop_runs_queued_task_to_completion() -> None:
    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        return _success_result()

    loop = RuntimeAutonomousTaskLoop(runner=runner)
    loop.submit("update zero_probe.txt with queued data")

    result = loop.run_once()

    assert result["schema"] == RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA
    assert result["ok"] is True
    assert result["loop_status"] == "completed"
    assert result["task"]["status"] == "completed"
    assert calls == ["update zero_probe.txt with queued data"]


def test_autonomous_loop_marks_failed_task() -> None:
    def runner(goal: str) -> dict:
        return _failed_result()

    loop = RuntimeAutonomousTaskLoop(runner=runner)
    loop.submit("update zero_probe.txt with bad data")

    result = loop.run_once()

    assert result["ok"] is False
    assert result["loop_status"] == "failed"
    assert result["task"]["status"] == "failed"
    assert result["task"]["denial_reason"] == "forced_failure"


def test_autonomous_loop_run_until_idle_processes_multiple_tasks() -> None:
    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        return _success_result()

    loop = RuntimeAutonomousTaskLoop(runner=runner, max_tasks=5)
    loop.submit("update a.txt with one")
    loop.submit("update b.txt with two")

    result = loop.run_until_idle()

    assert result["ok"] is True
    assert result["loop_status"] == "idle"
    assert result["completed_count"] == 2
    assert result["failed_count"] == 0
    assert result["queued_count"] == 0
    assert calls == [
        "update a.txt with one",
        "update b.txt with two",
    ]

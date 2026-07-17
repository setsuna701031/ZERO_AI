from __future__ import annotations

from core.runtime.runtime_autonomous_operator_bridge import (
    RUNTIME_AUTONOMOUS_OPERATOR_BRIDGE_SCHEMA,
    RuntimeAutonomousOperatorBridge,
)


def _success(goal: str) -> dict:
    return {
        "ok": True,
        "natural_task": goal,
        "repair_loop_status": "completed",
        "operator_result": {
            "controlled_mutation_result": {
                "ok": True,
                "mutation_completed": True,
                "validation_passed": True,
                "changed_files": ["zero_probe.txt"],
            }
        },
    }


def _repair_success(goal: str) -> dict:
    return {
        "ok": True,
        "natural_task": goal,
        "repair_loop_status": "repaired",
        "repair_attempted": True,
        "operator_result": {
            "controlled_mutation_result": {
                "ok": True,
                "mutation_completed": True,
                "validation_passed": True,
                "changed_files": ["zero_probe.txt"],
            }
        },
    }


def _failure(goal: str) -> dict:
    return {
        "ok": False,
        "natural_task": goal,
        "denial_reason": "runner_failed",
        "operator_result": {
            "controlled_mutation_result": {
                "ok": False,
                "mutation_completed": False,
                "validation_passed": False,
            }
        },
    }


def test_bridge_submit_queues_task() -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_success)
    result = bridge.submit("update zero_probe.txt with bridge data")

    assert result["schema"] == RUNTIME_AUTONOMOUS_OPERATOR_BRIDGE_SCHEMA
    assert result["ok"] is True
    assert result["bridge_status"] == "queued"
    assert result["queue_depth"] == 1
    assert result["task"]["goal"] == "update zero_probe.txt with bridge data"


def test_bridge_run_once_executes_queued_task_with_runner() -> None:
    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        return _success(goal)

    bridge = RuntimeAutonomousOperatorBridge(runner=runner)
    bridge.submit("update zero_probe.txt with bridge data")

    result = bridge.run_once()

    assert result["schema"] == RUNTIME_AUTONOMOUS_OPERATOR_BRIDGE_SCHEMA
    assert result["ok"] is True
    assert result["bridge_status"] == "completed"
    assert result["task"]["status"] == "completed"
    assert calls == ["update zero_probe.txt with bridge data"]


def test_bridge_run_until_idle_processes_multiple_tasks() -> None:
    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        return _success(goal)

    bridge = RuntimeAutonomousOperatorBridge(runner=runner, max_tasks=5)
    bridge.submit("update zero_probe.txt with first")
    bridge.submit("append second to zero_probe.txt")

    result = bridge.run_until_idle()

    assert result["schema"] == RUNTIME_AUTONOMOUS_OPERATOR_BRIDGE_SCHEMA
    assert result["ok"] is True
    assert result["bridge_status"] == "idle"
    assert result["completed_count"] == 2
    assert result["failed_count"] == 0
    assert calls == [
        "update zero_probe.txt with first",
        "append second to zero_probe.txt",
    ]


def test_bridge_accepts_repaired_runner_result_as_success() -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_repair_success)
    bridge.submit(
        "update zero_probe.txt with broken data force validation failure"
    )

    result = bridge.run_once()

    assert result["ok"] is True
    assert result["bridge_status"] == "completed"
    assert result["task"]["status"] == "completed"
    assert result["result"]["repair_loop_status"] == "repaired"


def test_bridge_marks_failed_runner_result() -> None:
    bridge = RuntimeAutonomousOperatorBridge(runner=_failure)
    bridge.submit("update zero_probe.txt with bad data")

    result = bridge.run_once()

    assert result["ok"] is False
    assert result["bridge_status"] == "failed"
    assert result["task"]["status"] == "failed"
    assert result["task"]["denial_reason"] == "runner_failed"

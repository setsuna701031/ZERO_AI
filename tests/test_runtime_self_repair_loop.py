from __future__ import annotations

from core.runtime.runtime_self_repair_loop import (
    RUNTIME_SELF_REPAIR_LOOP_SCHEMA,
    RuntimeSelfRepairLoop,
    build_repair_task,
)


def _failed_result() -> dict:
    return {
        "ok": True,
        "operator_result": {
            "controlled_mutation_result": {
                "ok": False,
                "mutation_started": True,
                "mutation_completed": False,
                "validation_passed": False,
                "rollback_completed": True,
                "denial_reason": "console_filesystem_mutation_incomplete",
                "non_mainline_issues": [
                    "forced_validation_failure:zero_probe.txt"
                ],
            },
            "governed_runtime_result": {
                "non_mainline_issues": [
                    "forced_validation_failure:zero_probe.txt"
                ],
            },
        },
    }


def _success_result() -> dict:
    return {
        "ok": True,
        "operator_result": {
            "controlled_mutation_result": {
                "ok": True,
                "mutation_started": True,
                "mutation_completed": True,
                "validation_passed": True,
                "changed_files": ["zero_probe.txt"],
            },
        },
    }


def test_build_repair_task_removes_failure_injection_marker() -> None:
    repair = build_repair_task(
        "update zero_probe.txt with broken data force validation failure",
        _failed_result(),
    )

    assert repair["schema"] == RUNTIME_SELF_REPAIR_LOOP_SCHEMA
    assert repair["ok"] is True
    assert repair["repair_required"] is True
    assert repair["repair_goal"] == "update zero_probe.txt with broken data"
    assert repair["denial_reason"] == "console_filesystem_mutation_incomplete"
    assert "forced_validation_failure:zero_probe.txt" in repair["non_mainline_issues"]


def test_self_repair_loop_completes_without_repair_when_first_attempt_passes() -> None:
    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        return _success_result()

    loop = RuntimeSelfRepairLoop(runner=runner, max_attempts=2)
    result = loop.run("update zero_probe.txt with stable data")

    assert result["schema"] == RUNTIME_SELF_REPAIR_LOOP_SCHEMA
    assert result["ok"] is True
    assert result["loop_status"] == "completed"
    assert result["repair_attempted"] is False
    assert result["final_goal"] == "update zero_probe.txt with stable data"
    assert calls == ["update zero_probe.txt with stable data"]


def test_self_repair_loop_retries_repaired_goal_after_failure() -> None:
    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        if "force validation failure" in goal:
            return _failed_result()
        return _success_result()

    loop = RuntimeSelfRepairLoop(runner=runner, max_attempts=2)
    result = loop.run(
        "update zero_probe.txt with broken data force validation failure"
    )

    assert result["schema"] == RUNTIME_SELF_REPAIR_LOOP_SCHEMA
    assert result["ok"] is True
    assert result["loop_status"] == "repaired"
    assert result["repair_attempted"] is True
    assert result["final_goal"] == "update zero_probe.txt with broken data"
    assert calls == [
        "update zero_probe.txt with broken data force validation failure",
        "update zero_probe.txt with broken data",
    ]
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["ok"] is False
    assert result["attempts"][1]["ok"] is True


def test_self_repair_loop_reports_failed_when_repair_exhausted() -> None:
    def runner(goal: str) -> dict:
        return _failed_result()

    loop = RuntimeSelfRepairLoop(runner=runner, max_attempts=2)
    result = loop.run(
        "update zero_probe.txt with broken data force validation failure"
    )

    assert result["schema"] == RUNTIME_SELF_REPAIR_LOOP_SCHEMA
    assert result["ok"] is False
    assert result["loop_status"] == "failed"
    assert result["repair_attempted"] is True
    assert len(result["attempts"]) == 2
    assert result["denial_reason"] == "console_filesystem_mutation_incomplete"

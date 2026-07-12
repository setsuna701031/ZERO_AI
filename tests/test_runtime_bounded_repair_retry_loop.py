from __future__ import annotations

import copy

import pytest

from core.runtime.runtime_bounded_repair_retry_loop import (
    RuntimeBoundedRepairRetryLoop,
)
from core.runtime.runtime_repair_advisor import RuntimeRepairAdvisor


def _loop(runner, **kwargs):
    return RuntimeBoundedRepairRetryLoop(
        task_runner=runner,
        repair_advisor=RuntimeRepairAdvisor(),
        allow_bounded_retry=True,
        **kwargs,
    )


def test_first_success_does_not_retry() -> None:
    calls: list[str] = []
    result = _loop(
        lambda goal: calls.append(goal) or {"ok": True, "validation_passed": True}
    ).run("same goal")

    assert result["loop_status"] == "completed"
    assert result["attempts_completed"] == 1
    assert result["retry_count"] == 0
    assert calls == ["same goal"]


@pytest.mark.parametrize("failure", [
    {"ok": False, "validation_passed": False},
    {"ok": False, "mutation_completed": False},
])
def test_retryable_failure_then_success_reuses_exact_goal(failure: dict) -> None:
    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        return failure if len(calls) == 1 else {"ok": True, "validation_passed": True}

    result = _loop(runner, max_attempts=2).run("same goal")

    assert result["loop_status"] == "completed_after_retry"
    assert result["retry_count"] == 1
    assert calls == ["same goal", "same goal"]
    assert all(item["original_goal"] == item["executed_goal"] == "same goal" for item in result["attempt_results"])
    assert all(item["goal_unchanged"] is True for item in result["attempt_results"])


def test_retry_exhaustion_never_exceeds_max_attempts() -> None:
    calls: list[str] = []
    result = _loop(
        lambda goal: calls.append(goal) or {"ok": False, "validation_passed": False},
        max_attempts=3,
    ).run("same goal")

    assert result["loop_status"] == "failed_retry_exhausted"
    assert result["stopped_reason"] == "max_attempts_reached"
    assert result["attempts_completed"] == 3
    assert result["retry_count"] == 2
    assert len(calls) == 3


@pytest.mark.parametrize("runner", [
    lambda goal: {"ok": False, "denial_reason": "unsafe_path"},
    lambda goal: {"ok": False, "denial_reason": "mutation adapter unavailable"},
    lambda goal: {"ok": False, "denial_reason": "mutation adapter incomplete"},
    lambda goal: {"ok": False, "rollback_required": True, "rollback_completed": False},
    lambda goal: {"ok": False, "denial_reason": "unclassified"},
])
def test_forbidden_categories_do_not_retry(runner) -> None:
    result = _loop(runner).run("same goal")
    assert result["loop_status"] == "failed_not_retryable"
    assert result["attempts_completed"] == 1
    assert result["attempt_results"][0]["retry_admitted"] is False


def test_observation_failure_does_not_retry() -> None:
    result = RuntimeBoundedRepairRetryLoop(
        task_runner=lambda goal: {"ok": False},
        observer=lambda **kwargs: {
            "observer_status": "observer_error", "observation_complete": False
        },
        repair_advisor=RuntimeRepairAdvisor(),
        allow_bounded_retry=True,
    ).run("same goal")
    assert result["attempts_completed"] == 1
    assert result["repair_advice"]["failure_category"] == "observation_failure"


def test_runner_exception_requires_explicit_permission() -> None:
    calls: list[str] = []

    def runner(goal: str) -> dict:
        calls.append(goal)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return {"ok": True, "validation_passed": True}

    denied = _loop(runner).run("same goal")
    calls.clear()
    allowed = _loop(runner, allow_runner_exception_retry=True).run("same goal")

    assert denied["loop_status"] == "runner_error"
    assert denied["attempts_completed"] == 1
    assert allowed["loop_status"] == "completed_after_retry"
    assert allowed["attempts_completed"] == 2


def test_configuration_and_max_attempts_one_are_bounded() -> None:
    invalid = _loop(lambda goal: {"ok": True}, max_attempts=0).run("goal")
    one = _loop(
        lambda goal: {"ok": False, "validation_passed": False}, max_attempts=1
    ).run("goal")

    assert invalid["loop_status"] == "denied_invalid_configuration"
    assert invalid["attempts_completed"] == 0
    assert one["loop_status"] == "failed_retry_exhausted"
    assert one["attempts_completed"] == 1


@pytest.mark.parametrize("advisor", [
    None,
    lambda **kwargs: (_ for _ in ()).throw(RuntimeError("advisor")),
    lambda **kwargs: {
        "advisor_status": "repair_not_needed", "repair_needed": False,
        "repairability": "not_applicable", "repair_execution_allowed": False,
        "autonomous_retry_allowed": False, "failure_category": "none",
    },
    lambda **kwargs: {
        "advisor_status": "manual_review_required", "repair_needed": True,
        "repairability": "manual_only", "repair_execution_allowed": False,
        "autonomous_retry_allowed": False, "failure_category": "validation_failure",
    },
])
def test_missing_error_or_nonrepairable_advisor_never_retries(advisor) -> None:
    result = RuntimeBoundedRepairRetryLoop(
        task_runner=lambda goal: {"ok": False, "validation_passed": False},
        repair_advisor=advisor,
        allow_bounded_retry=True,
    ).run("goal")
    assert result["attempts_completed"] == 1
    assert result["loop_status"] == "failed_not_retryable"


def test_explicit_bounded_permission_is_required() -> None:
    result = RuntimeBoundedRepairRetryLoop(
        task_runner=lambda goal: {"ok": False, "validation_passed": False},
        repair_advisor=RuntimeRepairAdvisor(),
        allow_bounded_retry=False,
    ).run("goal")
    assert result["attempts_completed"] == 1
    assert result["attempt_results"][0]["retry_denial_reason"] == "bounded_retry_not_explicitly_allowed"


def test_task_metadata_and_requested_changes_are_not_modified() -> None:
    task = {
        "task_id": "one", "goal": "same goal",
        "metadata": {"memory_context": {"experience_count": 1}},
        "requested_changes": [{"change_id": "change-1"}],
    }
    before = copy.deepcopy(task)
    result = _loop(
        lambda goal: {"ok": False, "validation_passed": False}, max_attempts=2
    ).run(task)

    assert task == before
    assert result["requested_changes_modified"] is False
    assert result["autonomous_task_creation"] is False
    assert result["patch_generation_allowed"] is False
    assert result["runtime_loop_closed"] is True
    assert all(item["metadata"] == task["metadata"] for item in result["attempt_results"])

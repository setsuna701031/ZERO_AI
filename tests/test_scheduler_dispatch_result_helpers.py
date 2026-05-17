from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from core.tasks.scheduler_core.dispatch_finalize import (
    _extract_dispatch_failure_error,
    apply_finalize_decision,
    build_finalize_decision,
    extract_effective_status_and_answer,
)


class RecordingDispatcher:
    def __init__(self, calls: List[Dict[str, Any]]) -> None:
        self.calls = calls

    def complete_task(self, **kwargs: Any) -> None:
        self.calls.append({"method": "complete_task", **kwargs})

    def fail_task(self, **kwargs: Any) -> None:
        self.calls.append({"method": "fail_task", **kwargs})


class RecordingWorkerPool:
    def __init__(self, calls: List[Dict[str, Any]]) -> None:
        self.calls = calls

    def release_by_task(self, task_id: str) -> None:
        self.calls.append({"method": "release_by_task", "task_id": task_id})


class RecordingQueue:
    def __init__(self, calls: List[Dict[str, Any]]) -> None:
        self.calls = calls

    def requeue(self, **kwargs: Any) -> None:
        self.calls.append({"method": "requeue", **kwargs})


class FinalizeScheduler:
    def __init__(self, *, can_requeue: bool = True) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.dispatcher = RecordingDispatcher(self.calls)
        self.worker_pool = RecordingWorkerPool(self.calls)
        self.scheduler_queue = RecordingQueue(self.calls)
        self.can_requeue = can_requeue

    def _mark_repo_task_finished(self, **kwargs: Any) -> None:
        self.calls.append({"method": "_mark_repo_task_finished", **kwargs})

    def _mark_repo_task_failed(self, **kwargs: Any) -> None:
        self.calls.append({"method": "_mark_repo_task_failed", **kwargs})

    def _mark_repo_task_queued(self, **kwargs: Any) -> None:
        self.calls.append({"method": "_mark_repo_task_queued", **kwargs})

    def _sync_blocked_state(self, **kwargs: Any) -> None:
        self.calls.append({"method": "_sync_blocked_state", **kwargs})

    def _can_requeue_task(self, task_id: str) -> bool:
        self.calls.append({"method": "_can_requeue_task", "task_id": task_id})
        return self.can_requeue


def test_extract_effective_status_prefers_runner_result() -> None:
    status, final_answer = extract_effective_status_and_answer(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "running", "final_answer": "refreshed"},
        runner_result={"status": "FINISHED", "final_answer": "runner"},
    )

    assert status == "finished"
    assert final_answer == "runner"


def test_extract_effective_status_falls_back_to_refreshed_task() -> None:
    status, final_answer = extract_effective_status_and_answer(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "FAILED", "final_answer": "refreshed"},
        runner_result={"ok": False, "final_answer": ""},
    )

    assert status == "failed"
    assert final_answer == "refreshed"


def test_extract_effective_status_falls_back_to_original_task() -> None:
    status, final_answer = extract_effective_status_and_answer(
        original_task={"status": "BLOCKED", "final_answer": "original"},
        refreshed_task={"status": "", "final_answer": ""},
        runner_result={"status": "", "final_answer": ""},
    )

    assert status == "blocked"
    assert final_answer == "original"


def test_extract_effective_final_answer_skips_empty_values() -> None:
    status, final_answer = extract_effective_status_and_answer(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "", "final_answer": None},
        runner_result={"status": "", "final_answer": ""},
    )

    assert status == "queued"
    assert final_answer == "original"


def test_extract_effective_status_handles_missing_payloads() -> None:
    status, final_answer = extract_effective_status_and_answer(
        original_task=None,
        refreshed_task=None,
        runner_result=None,
    )

    assert status == ""
    assert final_answer == ""


def test_extract_effective_status_ignores_non_dict_payloads() -> None:
    status, final_answer = extract_effective_status_and_answer(
        original_task="bad",
        refreshed_task=["bad"],
        runner_result=("bad",),
    )

    assert status == ""
    assert final_answer == ""


def test_extract_effective_status_normalizes_status_whitespace() -> None:
    status, final_answer = extract_effective_status_and_answer(
        original_task={"status": " queued ", "final_answer": " original "},
        refreshed_task={"status": " running ", "final_answer": " refreshed "},
        runner_result={"status": " FINISHED ", "final_answer": " runner "},
    )

    assert status == "finished"
    assert final_answer == " runner "


def test_extract_effective_final_answer_prefers_runner_over_refreshed_and_original() -> None:
    status, final_answer = extract_effective_status_and_answer(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "running", "final_answer": "refreshed"},
        runner_result={"status": "", "final_answer": "runner"},
    )

    assert status == "running"
    assert final_answer == "runner"


def test_extract_effective_status_does_not_use_effective_status_key_yet() -> None:
    status, final_answer = extract_effective_status_and_answer(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "running", "final_answer": "refreshed"},
        runner_result={"effective_status": "FAILED", "final_answer": "runner"},
    )

    assert status == "running"
    assert final_answer == "runner"


def test_build_finalize_decision_returns_finish_action_without_writes() -> None:
    decision = build_finalize_decision(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "running", "final_answer": "refreshed"},
        runner_result={"status": "completed", "final_answer": "runner", "ok": True},
        status_blocked="blocked",
        status_finished="finished",
        status_failed="failed",
    )

    assert decision == {
        "action": "finish",
        "status": "completed",
        "final_answer": "runner",
        "fail_error": "",
        "blocked_reason": "",
        "queue_error": "",
        "ok": True,
    }


def test_build_finalize_decision_extracts_failure_error_precedence() -> None:
    decision = build_finalize_decision(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "running", "final_answer": "refreshed"},
        runner_result={
            "status": "failed",
            "final_answer": "runner",
            "error": "runner error",
            "ok": False,
        },
        status_blocked="blocked",
        status_finished="finished",
        status_failed="failed",
    )

    assert decision["action"] == "fail"
    assert decision["status"] == "failed"
    assert decision["final_answer"] == "runner"
    assert decision["fail_error"] == "runner error"
    assert decision["ok"] is False


def test_extract_dispatch_failure_error_prefers_runner_error() -> None:
    error = _extract_dispatch_failure_error(
        {"error": "runner error"},
        "final answer",
        default="default error",
    )

    assert error == "runner error"


def test_extract_dispatch_failure_error_falls_back_to_final_answer() -> None:
    error = _extract_dispatch_failure_error(
        {"error": ""},
        "final answer",
        default="default error",
    )

    assert error == "final answer"


def test_extract_dispatch_failure_error_uses_default_last() -> None:
    error = _extract_dispatch_failure_error(
        {"error": ""},
        "",
        default="default error",
    )

    assert error == "default error"


def test_build_finalize_decision_classifies_requeue_candidate() -> None:
    decision = build_finalize_decision(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "ready", "final_answer": ""},
        runner_result={"status": "", "final_answer": ""},
        status_blocked="blocked",
        status_finished="finished",
        status_failed="failed",
    )

    assert decision["action"] == "requeue_if_ready"
    assert decision["status"] == "ready"
    assert decision["final_answer"] == "original"
    assert decision["queue_error"] == ""


def test_build_finalize_decision_classifies_blocked_action() -> None:
    decision = build_finalize_decision(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "blocked", "final_answer": ""},
        runner_result={
            "status": "blocked",
            "blocked_reason": "dependency missing",
            "ok": False,
        },
        status_blocked="blocked",
        status_finished="finished",
        status_failed="failed",
    )

    assert decision["action"] == "block"
    assert decision["status"] == "blocked"
    assert decision["blocked_reason"] == "dependency missing"
    assert decision["ok"] is False


def test_build_finalize_decision_blocked_reason_falls_back_to_error() -> None:
    decision = build_finalize_decision(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "blocked", "final_answer": ""},
        runner_result={
            "status": "blocked",
            "error": "blocked by runtime",
            "ok": False,
        },
        status_blocked="blocked",
        status_finished="finished",
        status_failed="failed",
    )

    assert decision["action"] == "block"
    assert decision["blocked_reason"] == "blocked by runtime"


def test_build_finalize_decision_does_not_use_effective_status_key_yet() -> None:
    decision = build_finalize_decision(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "running", "final_answer": "refreshed"},
        runner_result={
            "status": "running",
            "effective_status": "FAILED",
            "final_answer": "runner",
            "error": "effective failure",
            "ok": False,
        },
        status_blocked="blocked",
        status_finished="finished",
        status_failed="failed",
    )

    assert decision["action"] == "requeue_if_ready"
    assert decision["status"] == "running"
    assert decision["final_answer"] == "runner"


def test_apply_finalize_decision_dispatches_finish_side_effects() -> None:
    scheduler = FinalizeScheduler()

    apply_finalize_decision(
        scheduler=scheduler,
        task_id="task-1",
        scheduled_task=SimpleNamespace(priority=3),
        decision={"action": "finish", "final_answer": "done"},
    )

    assert scheduler.calls == [
        {"method": "complete_task", "task_id": "task-1", "result": "done"},
        {"method": "_mark_repo_task_finished", "task_id": "task-1", "result": "done"},
    ]


def test_apply_finalize_decision_dispatches_fail_side_effects() -> None:
    scheduler = FinalizeScheduler()

    apply_finalize_decision(
        scheduler=scheduler,
        task_id="task-1",
        scheduled_task=SimpleNamespace(priority=3),
        decision={"action": "fail", "fail_error": "boom"},
    )

    assert scheduler.calls == [
        {
            "method": "fail_task",
            "task_id": "task-1",
            "error": "boom",
            "requeue_on_retry": False,
        },
        {"method": "_mark_repo_task_failed", "task_id": "task-1", "error": "boom"},
    ]


def test_apply_finalize_decision_dispatches_block_side_effects() -> None:
    scheduler = FinalizeScheduler()

    apply_finalize_decision(
        scheduler=scheduler,
        task_id="task-1",
        scheduled_task=SimpleNamespace(priority=3),
        decision={"action": "block", "blocked_reason": "waiting dependency"},
    )

    assert scheduler.calls == [
        {"method": "release_by_task", "task_id": "task-1"},
        {
            "method": "_sync_blocked_state",
            "task_id": "task-1",
            "blocked_reason": "waiting dependency",
        },
    ]


def test_apply_finalize_decision_dispatches_requeue_side_effects() -> None:
    scheduler = FinalizeScheduler(can_requeue=True)

    apply_finalize_decision(
        scheduler=scheduler,
        task_id="task-1",
        scheduled_task=SimpleNamespace(priority=3),
        decision={"action": "requeue_if_ready", "queue_error": "retry later"},
    )

    assert scheduler.calls == [
        {"method": "release_by_task", "task_id": "task-1"},
        {"method": "_can_requeue_task", "task_id": "task-1"},
        {"method": "requeue", "task_id": "task-1", "priority": 3},
        {"method": "_mark_repo_task_queued", "task_id": "task-1", "error": "retry later"},
    ]


def test_apply_finalize_decision_requeue_respects_can_requeue_gate() -> None:
    scheduler = FinalizeScheduler(can_requeue=False)

    apply_finalize_decision(
        scheduler=scheduler,
        task_id="task-1",
        scheduled_task=SimpleNamespace(priority=3),
        decision={"action": "requeue_if_ready", "queue_error": "retry later"},
    )

    assert scheduler.calls == [
        {"method": "release_by_task", "task_id": "task-1"},
        {"method": "_can_requeue_task", "task_id": "task-1"},
    ]


def test_apply_finalize_decision_dispatches_default_release_side_effect() -> None:
    scheduler = FinalizeScheduler()

    apply_finalize_decision(
        scheduler=scheduler,
        task_id="task-1",
        scheduled_task=SimpleNamespace(priority=3),
        decision={"action": "release"},
    )

    assert scheduler.calls == [
        {"method": "release_by_task", "task_id": "task-1"},
    ]

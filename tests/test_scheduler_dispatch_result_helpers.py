from __future__ import annotations

from core.tasks.scheduler_core.dispatch_result_helpers import (
    build_finalize_decision,
    extract_effective_status_and_answer,
)


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
        "ok": True,
    }


def test_build_finalize_decision_extracts_failure_error_precedence() -> None:
    decision = build_finalize_decision(
        original_task={"status": "queued", "final_answer": "original"},
        refreshed_task={"status": "running", "final_answer": "refreshed"},
        runner_result={"status": "failed", "final_answer": "runner", "error": "runner error", "ok": False},
        status_blocked="blocked",
        status_finished="finished",
        status_failed="failed",
    )

    assert decision["action"] == "fail"
    assert decision["status"] == "failed"
    assert decision["final_answer"] == "runner"
    assert decision["fail_error"] == "runner error"
    assert decision["ok"] is False


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

from __future__ import annotations

from core.tasks.scheduler_core.dispatch_result_helpers import extract_effective_status_and_answer


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

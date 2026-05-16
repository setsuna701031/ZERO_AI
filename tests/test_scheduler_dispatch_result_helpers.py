from __future__ import annotations

from core.tasks.scheduler_core.dispatch_result_helpers import (
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
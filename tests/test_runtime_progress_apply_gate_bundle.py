from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_progress_apply_gate import (
    build_runtime_progress_apply_record,
)


ROOT = Path(__file__).resolve().parents[1]


def _authority(**overrides):
    record = {
        "execution_lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "capability_grant_id": "capability-grant::limited-runtime-session::birth-1209::capability-1225",
        "executor_binding_id": "executor-binding::executor-zero::binding-1233",
    }
    record.update(overrides)
    return {key: value for key, value in record.items() if value is not None}


def _commit_result(
    *,
    commit_completed: bool = True,
    result_kind: str = "read_result",
    summary: str = "caller supplied read evidence",
    failure_reason: str = "none",
    recovery_required: bool = False,
    execution_lease_id: str | None = "execution-lease::limited-runtime-session::birth-1209::lease-1217",
    capability_grant_id: str | None = "capability-grant::limited-runtime-session::birth-1209::capability-1225",
    executor_binding_id: str | None = "executor-binding::executor-zero::binding-1233",
):
    record = {
        "schema": "zero.runtime.step_commit_runner.v1",
        "step_commit_result_id": f"runtime-step-commit-result::session-1513::{result_kind}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_invocation_record_id": (
            f"runtime-step-commit-invocation::session-1513::{result_kind}"
        ),
        "source_authority_record_id": (
            f"runtime-step-commit-authority::session-1513::{result_kind}"
        ),
        "source_step_result_commit_request_id": (
            f"runtime-step-result-commit-request::session-1513::{result_kind}"
        ),
        "commit_completed": commit_completed,
        "commit_denied": not commit_completed,
        "denial_reason": "none" if commit_completed else "commit_not_authorized",
        "result_kind": result_kind,
        "result_summary": summary,
        "summary": summary,
        "failure_reason": failure_reason,
        "recovery_required": recovery_required,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "progress_updated": False,
        "cursor_advanced": False,
    }
    return {key: value for key, value in record.items() if value is not None}


def test_1513_completed_commit_creates_progress_record():
    record = build_runtime_progress_apply_record(
        _commit_result(),
        authority=_authority(),
    )

    assert record["progress_apply_allowed"] is True
    assert record["progress_record_created"] is True
    assert record["progress_apply_denied"] is False
    assert record["denial_reason"] == "none"
    assert record["source_step_commit_result_id"].startswith(
        "runtime-step-commit-result::"
    )


def test_1514_incomplete_commit_denied():
    record = build_runtime_progress_apply_record(
        _commit_result(commit_completed=False),
        authority=_authority(),
    )

    assert record["progress_apply_allowed"] is False
    assert record["progress_record_created"] is False
    assert record["progress_apply_denied"] is True
    assert record["denial_reason"] == "commit_not_authorized"


def test_1515_missing_authority_denied():
    record = build_runtime_progress_apply_record(
        _commit_result(execution_lease_id=None),
        authority=_authority(execution_lease_id=None),
    )

    assert record["progress_apply_allowed"] is False
    assert record["progress_record_created"] is False
    assert record["denial_reason"] == "missing_authority:execution_lease_id"
    assert record["missing_authority"] == ["execution_lease_id"]


def test_1516_result_metadata_preserved():
    record = build_runtime_progress_apply_record(
        _commit_result(
            result_kind="failure_result",
            summary="caller supplied failure evidence",
            failure_reason="executor_reported_failure",
            recovery_required=True,
        ),
        authority=_authority(),
    )

    assert record["progress_apply_allowed"] is True
    assert record["result_kind"] == "failure_result"
    assert record["summary"] == "caller supplied failure evidence"
    assert record["result_summary"] == "caller supplied failure evidence"
    assert record["failure_reason"] == "executor_reported_failure"
    assert record["recovery_required"] is True


def test_1517_deterministic_denied_output():
    commit = _commit_result(commit_completed=False)

    first = build_runtime_progress_apply_record(commit, authority=_authority())
    second = build_runtime_progress_apply_record(commit, authority=_authority())

    assert first == second
    assert first["progress_apply_allowed"] is False
    assert first["progress_apply_record_id"].startswith("runtime-progress-apply::")


def test_1518_cursor_advanced_remains_false():
    record = build_runtime_progress_apply_record(
        _commit_result(),
        authority=_authority(),
    )

    assert record["cursor_advanced"] is False


def test_1519_next_tick_requested_remains_false():
    record = build_runtime_progress_apply_record(
        _commit_result(),
        authority=_authority(),
    )

    assert record["next_tick_requested"] is False
    assert record["loop_continued"] is False
    assert record["automatic_retry_performed"] is False
    assert record["daemon_started"] is False
    assert record["thread_created"] is False


def test_1520_executor_and_scheduler_not_imported():
    source = (ROOT / "core/runtime/runtime_progress_apply_gate.py").read_text()
    record = build_runtime_progress_apply_record(
        _commit_result(),
        authority=_authority(),
    )

    assert "import executor" not in source
    assert "from core.runtime.executor" not in source
    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert "runtime_progress_memory" not in source
    assert "runtime_resume_cursor" not in source
    assert record["executor_imported"] is False
    assert record["scheduler_imported"] is False

from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_step_commit_runner import (
    build_runtime_step_commit_result_record,
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


def _invocation(
    *,
    commit_invocation_ready: bool = True,
    result_kind: str = "read_result",
    summary: str = "caller supplied read evidence",
    failure_reason: str = "none",
    recovery_required: bool = False,
    execution_lease_id: str | None = "execution-lease::limited-runtime-session::birth-1209::lease-1217",
    capability_grant_id: str | None = "capability-grant::limited-runtime-session::birth-1209::capability-1225",
    executor_binding_id: str | None = "executor-binding::executor-zero::binding-1233",
):
    record = {
        "schema": "zero.runtime.step_commit_execution_adapter.v1",
        "invocation_record_id": f"runtime-step-commit-invocation::session-1497::{result_kind}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_authority_record_id": (
            f"runtime-step-commit-authority::session-1497::{result_kind}"
        ),
        "source_step_result_commit_request_id": (
            f"runtime-step-result-commit-request::session-1497::{result_kind}"
        ),
        "commit_authorized": commit_invocation_ready,
        "commit_invocation_ready": commit_invocation_ready,
        "blocked_reason": "none" if commit_invocation_ready else "commit_not_authorized",
        "result_kind": result_kind,
        "result_summary": summary,
        "summary": summary,
        "failure_reason": failure_reason,
        "recovery_required": recovery_required,
        "execution_lease_id": execution_lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "committed": False,
        "progress_updated": False,
        "cursor_advanced": False,
    }
    return {key: value for key, value in record.items() if value is not None}


def test_1497_authorized_invocation_creates_commit_completed_true():
    record = build_runtime_step_commit_result_record(
        _invocation(),
        authority=_authority(),
    )

    assert record["commit_completed"] is True
    assert record["commit_denied"] is False
    assert record["denial_reason"] == "none"
    assert record["result_kind"] == "read_result"
    assert record["summary"] == "caller supplied read evidence"


def test_1498_denied_invocation_creates_deterministic_denied_record():
    invocation = _invocation(commit_invocation_ready=False)

    first = build_runtime_step_commit_result_record(invocation, authority=_authority())
    second = build_runtime_step_commit_result_record(invocation, authority=_authority())

    assert first == second
    assert first["commit_completed"] is False
    assert first["commit_denied"] is True
    assert first["denial_reason"] == "commit_not_authorized"
    assert first["step_commit_result_id"].startswith("runtime-step-commit-result::")


def test_1499_missing_lease_denies():
    record = build_runtime_step_commit_result_record(
        _invocation(execution_lease_id=None),
        authority=_authority(execution_lease_id=None),
    )

    assert record["commit_completed"] is False
    assert record["commit_denied"] is True
    assert record["denial_reason"] == "missing_authority:execution_lease_id"
    assert record["missing_authority"] == ["execution_lease_id"]


def test_1500_missing_grant_denies():
    record = build_runtime_step_commit_result_record(
        _invocation(capability_grant_id=None),
        authority=_authority(capability_grant_id=None),
    )

    assert record["commit_completed"] is False
    assert record["commit_denied"] is True
    assert record["denial_reason"] == "missing_authority:capability_grant_id"
    assert record["missing_authority"] == ["capability_grant_id"]


def test_1501_missing_binding_denies():
    record = build_runtime_step_commit_result_record(
        _invocation(executor_binding_id=None),
        authority=_authority(executor_binding_id=None),
    )

    assert record["commit_completed"] is False
    assert record["commit_denied"] is True
    assert record["denial_reason"] == "missing_authority:executor_binding_id"
    assert record["missing_authority"] == ["executor_binding_id"]


def test_1502_failure_recovery_metadata_preserved():
    record = build_runtime_step_commit_result_record(
        _invocation(
            result_kind="failure_result",
            summary="caller supplied failure evidence",
            failure_reason="executor_reported_failure",
            recovery_required=True,
        ),
        authority=_authority(),
    )

    assert record["commit_completed"] is True
    assert record["result_kind"] == "failure_result"
    assert record["summary"] == "caller supplied failure evidence"
    assert record["failure_reason"] == "executor_reported_failure"
    assert record["recovery_required"] is True


def test_1503_progress_updated_remains_false():
    record = build_runtime_step_commit_result_record(
        _invocation(),
        authority=_authority(),
    )

    assert record["progress_updated"] is False
    assert record["progress_mutated"] is False


def test_1504_cursor_advanced_remains_false():
    record = build_runtime_step_commit_result_record(
        _invocation(),
        authority=_authority(),
    )

    assert record["cursor_advanced"] is False
    assert record["task_completion_mutated"] is False
    assert record["direct_file_mutation_performed"] is False


def test_1505_no_executor_import():
    source = (ROOT / "core/runtime/runtime_step_commit_runner.py").read_text()
    record = build_runtime_step_commit_result_record(
        _invocation(),
        authority=_authority(),
    )

    assert "import executor" not in source
    assert "from core.runtime.executor" not in source
    assert record["executor_imported"] is False
    assert record["executor_called"] is False


def test_1506_no_scheduler_import():
    source = (ROOT / "core/runtime/runtime_step_commit_runner.py").read_text()
    record = build_runtime_step_commit_result_record(
        _invocation(),
        authority=_authority(),
    )

    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert record["scheduler_imported"] is False
    assert record["scheduler_called"] is False
    assert record["retry_loop_started"] is False
    assert record["daemon_started"] is False
    assert record["thread_created"] is False

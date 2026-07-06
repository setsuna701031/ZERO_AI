from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_step_commit_authority_gate import (
    build_runtime_step_commit_authority_record,
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


def _request(
    *,
    commit_requested: bool = True,
    result_kind: str = "read_result",
    summary: str = "caller supplied read evidence",
    failure_reason: str = "none",
    recovery_required: bool = False,
):
    return {
        "schema": "zero.runtime.step_result_commit_bridge.v1",
        "step_result_commit_request_id": f"runtime-step-result-commit-request::session-1481::{result_kind}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_return_record_id": "runtime-execution-evidence-return::session-1481",
        "commit_requested": commit_requested,
        "result_kind": result_kind,
        "result_summary": summary,
        "summary": summary,
        "failure_reason": failure_reason,
        "recovery_required": recovery_required,
        "blocked_reason": "none" if commit_requested else "evidence_not_commit_ready",
        "committed": False,
        "progress_updated": False,
        "cursor_advanced": False,
    }


def test_1481_valid_request_with_authority_authorizes_commit():
    record = build_runtime_step_commit_authority_record(
        _request(),
        authority=_authority(),
    )

    assert record["commit_authorized"] is True
    assert record["denial_reason"] == "none"
    assert record["result_kind"] == "read_result"
    assert record["summary"] == "caller supplied read evidence"


def test_1482_missing_lease_grant_binding_denies():
    record = build_runtime_step_commit_authority_record(_request(), authority={})

    assert record["commit_authorized"] is False
    assert record["denial_reason"] == (
        "missing_authority:execution_lease_id,capability_grant_id,executor_binding_id"
    )
    assert record["missing_authority"] == [
        "execution_lease_id",
        "capability_grant_id",
        "executor_binding_id",
    ]


def test_1483_blocked_request_denies():
    record = build_runtime_step_commit_authority_record(
        _request(commit_requested=False),
        authority=_authority(),
    )

    assert record["commit_authorized"] is False
    assert record["denial_reason"] == "evidence_not_commit_ready"


def test_1484_failure_recovery_preserved():
    record = build_runtime_step_commit_authority_record(
        _request(
            result_kind="failure_result",
            summary="caller supplied failure evidence",
            failure_reason="executor_reported_failure",
            recovery_required=True,
        ),
        authority=_authority(),
    )

    assert record["commit_authorized"] is True
    assert record["result_kind"] == "failure_result"
    assert record["failure_reason"] == "executor_reported_failure"
    assert record["recovery_required"] is True


def test_1485_deterministic_authority_record():
    request = _request(result_kind="write_result", summary="caller supplied write evidence")
    authority = _authority()

    first = build_runtime_step_commit_authority_record(request, authority=authority)
    second = build_runtime_step_commit_authority_record(request, authority=authority)

    assert first == second
    assert first["authority_record_id"].startswith("runtime-step-commit-authority::")


def test_1486_committed_remains_false():
    record = build_runtime_step_commit_authority_record(
        _request(),
        authority=_authority(),
    )

    assert record["committed"] is False
    assert record["progress_updated"] is False
    assert record["cursor_advanced"] is False
    assert record["step_result_commit_called"] is False


def test_1487_no_executor_import():
    source = (ROOT / "core/runtime/runtime_step_commit_authority_gate.py").read_text()
    record = build_runtime_step_commit_authority_record(
        _request(),
        authority=_authority(),
    )

    assert "import executor" not in source
    assert "from core.runtime.executor" not in source
    assert record["executor_imported"] is False


def test_1488_no_scheduler_import():
    source = (ROOT / "core/runtime/runtime_step_commit_authority_gate.py").read_text()
    record = build_runtime_step_commit_authority_record(
        _request(),
        authority=_authority(),
    )

    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert record["scheduler_imported"] is False
    assert record["progress_mutated"] is False
    assert record["loop_continued"] is False
    assert record["automatic_retry_performed"] is False
    assert record["thread_created"] is False

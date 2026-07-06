from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_step_result_commit_bridge import (
    build_runtime_step_result_commit_request_bridge,
)


ROOT = Path(__file__).resolve().parents[1]


def _return_record(
    *,
    commit_ready: bool = True,
    result_kind: str = "read_result",
    summary: str = "caller supplied read evidence",
    failure_reason: str = "none",
    recovery_required: bool = False,
):
    return {
        "schema": "zero.runtime.execution_evidence_return_path.v1",
        "return_record_id": f"runtime-execution-evidence-return::session-1473::{result_kind}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_binding_record_id": "runtime-executor-binding-record::session-1473",
        "evidence_accepted": commit_ready,
        "result_kind": result_kind,
        "summary": summary,
        "failure_reason": failure_reason,
        "recovery_required": recovery_required,
        "commit_ready": commit_ready,
        "executor_called": False,
        "execution_inferred": False,
        "commit_input": {
            "result_kind": result_kind,
            "result_summary": summary,
            "failure_reason": failure_reason,
            "recovery_required": recovery_required,
        }
        if commit_ready
        else {},
    }


def test_1473_valid_return_record_creates_commit_request():
    request = build_runtime_step_result_commit_request_bridge(_return_record())

    assert request["commit_requested"] is True
    assert request["result_kind"] == "read_result"
    assert request["summary"] == "caller supplied read evidence"
    assert request["blocked_reason"] == "none"


def test_1474_missing_evidence_blocks():
    request = build_runtime_step_result_commit_request_bridge(
        _return_record(commit_ready=False)
    )

    assert request["commit_requested"] is False
    assert request["blocked_reason"] == "evidence_not_commit_ready"
    assert request["committed"] is False


def test_1475_failure_reason_preserved():
    request = build_runtime_step_result_commit_request_bridge(
        _return_record(
            result_kind="failure_result",
            summary="caller supplied failure evidence",
            failure_reason="executor_reported_failure",
        )
    )

    assert request["commit_requested"] is True
    assert request["result_kind"] == "failure_result"
    assert request["failure_reason"] == "executor_reported_failure"


def test_1476_recovery_marker_preserved():
    request = build_runtime_step_result_commit_request_bridge(
        _return_record(
            result_kind="recovery_result",
            summary="caller supplied recovery evidence",
            recovery_required=True,
        )
    )

    assert request["commit_requested"] is True
    assert request["recovery_required"] is True
    assert request["result_kind"] == "recovery_result"


def test_1477_deterministic_request():
    record = _return_record(result_kind="write_result", summary="caller supplied write evidence")

    first = build_runtime_step_result_commit_request_bridge(record)
    second = build_runtime_step_result_commit_request_bridge(record)

    assert first == second
    assert first["step_result_commit_request_id"].startswith(
        "runtime-step-result-commit-request::"
    )


def test_1478_committed_remains_false():
    request = build_runtime_step_result_commit_request_bridge(_return_record())

    assert request["committed"] is False
    assert request["progress_updated"] is False
    assert request["cursor_advanced"] is False
    assert request["step_result_commit_called"] is False


def test_1479_no_executor_import():
    source = (ROOT / "core/runtime/runtime_step_result_commit_bridge.py").read_text()
    request = build_runtime_step_result_commit_request_bridge(_return_record())

    assert "import executor" not in source
    assert "from core.runtime.executor" not in source
    assert "from core.runtime.runtime_step_result_commit" not in source
    assert "import runtime_step_result_commit" not in source
    assert request["executor_imported"] is False


def test_1480_no_scheduler_import():
    source = (ROOT / "core/runtime/runtime_step_result_commit_bridge.py").read_text()
    request = build_runtime_step_result_commit_request_bridge(_return_record())

    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert request["scheduler_imported"] is False
    assert request["progress_mutated"] is False
    assert request["loop_continued"] is False
    assert request["automatic_retry_performed"] is False
    assert request["thread_created"] is False

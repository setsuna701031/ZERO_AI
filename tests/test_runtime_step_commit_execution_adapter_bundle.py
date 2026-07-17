from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from core.runtime.runtime_step_commit_execution_adapter import (
    build_runtime_step_commit_invocation_record,
)


ROOT = Path(__file__).resolve().parents[1]


def _authority_record(
    *,
    commit_authorized: bool = True,
    result_kind: str = "read_result",
    summary: str = "caller supplied read evidence",
    failure_reason: str = "none",
    recovery_required: bool = False,
):
    return {
        "schema": "zero.runtime.step_commit_authority_gate.v1",
        "authority_record_id": f"runtime-step-commit-authority::session-1489::{result_kind}",
        "runtime_id": "limited-runtime-session::birth-1209",
        "source_step_result_commit_request_id": (
            f"runtime-step-result-commit-request::session-1489::{result_kind}"
        ),
        "commit_authorized": commit_authorized,
        "result_kind": result_kind,
        "result_summary": summary,
        "summary": summary,
        "failure_reason": failure_reason,
        "recovery_required": recovery_required,
        "execution_lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "capability_grant_id": "capability-grant::limited-runtime-session::birth-1209::capability-1225",
        "executor_binding_id": "executor-binding::executor-zero::binding-1233",
        "denial_reason": "none" if commit_authorized else "commit_not_requested",
        "committed": False,
        "progress_updated": False,
        "cursor_advanced": False,
    }


def test_1489_authorized_record_creates_invocation_envelope():
    record = build_runtime_step_commit_invocation_record(_authority_record())

    assert record["commit_invocation_ready"] is True
    assert record["commit_authorized"] is True
    assert record["blocked_reason"] == "none"
    assert record["source_authority_record_id"].startswith(
        "runtime-step-commit-authority::"
    )
    assert record["commit_invocation_envelope_only"] is True


def test_1490_denied_record_blocks():
    record = build_runtime_step_commit_invocation_record(
        _authority_record(commit_authorized=False)
    )

    assert record["commit_invocation_ready"] is False
    assert record["commit_authorized"] is False
    assert record["blocked_reason"] == "commit_not_requested"
    assert record["committed"] is False


def test_1491_failure_metadata_preserved():
    record = build_runtime_step_commit_invocation_record(
        _authority_record(
            result_kind="failure_result",
            summary="caller supplied failure evidence",
            failure_reason="executor_reported_failure",
        )
    )

    assert record["result_kind"] == "failure_result"
    assert record["summary"] == "caller supplied failure evidence"
    assert record["result_summary"] == "caller supplied failure evidence"
    assert record["failure_reason"] == "executor_reported_failure"


def test_1492_recovery_metadata_preserved():
    record = build_runtime_step_commit_invocation_record(
        _authority_record(
            result_kind="recovery_result",
            summary="caller supplied recovery evidence",
            recovery_required=True,
        )
    )

    assert record["result_kind"] == "recovery_result"
    assert record["summary"] == "caller supplied recovery evidence"
    assert record["recovery_required"] is True


def test_1493_deterministic_output():
    authority = _authority_record(result_kind="write_result")

    first = build_runtime_step_commit_invocation_record(authority)
    second = build_runtime_step_commit_invocation_record(authority)

    assert first == second
    assert first["invocation_record_id"].startswith(
        "runtime-step-commit-invocation::"
    )


def test_1494_no_progress_mutation():
    authority = _authority_record()
    before = deepcopy(authority)
    record = build_runtime_step_commit_invocation_record(authority)

    assert authority == before
    assert record["committed"] is False
    assert record["progress_updated"] is False
    assert record["cursor_advanced"] is False
    assert record["progress_mutated"] is False
    assert record["step_result_commit_called"] is False


def test_1495_no_executor_import():
    source = (
        ROOT / "core/runtime/runtime_step_commit_execution_adapter.py"
    ).read_text()
    record = build_runtime_step_commit_invocation_record(_authority_record())

    assert "import executor" not in source
    assert "from core.runtime.executor" not in source
    assert "runtime_step_result_commit" not in source
    assert record["executor_imported"] is False


def test_1496_no_scheduler_import():
    source = (
        ROOT / "core/runtime/runtime_step_commit_execution_adapter.py"
    ).read_text()
    record = build_runtime_step_commit_invocation_record(_authority_record())

    assert "import scheduler" not in source
    assert "from core.runtime.runtime_scheduler" not in source
    assert record["scheduler_imported"] is False
    assert record["loop_continued"] is False
    assert record["automatic_retry_performed"] is False
    assert record["thread_created"] is False

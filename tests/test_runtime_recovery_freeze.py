from __future__ import annotations

from pathlib import Path

from core.runtime.runtime_recovery_freeze import (
    assert_recovery_does_not_overwrite_source_transaction,
    assert_recovery_terminal_state,
    create_recovery_attempt,
    create_recovery_blocked_evidence,
    record_recovery_preflight,
    record_recovery_terminal_failure,
)
from core.runtime.runtime_surface_registry import classify_runtime_surface
from core.runtime.runtime_transaction_registry import create_transaction, get_transaction, list_transactions


def test_recovery_apply_requires_authority(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "recovery_apply", "original_transaction_id": "runtime_tx:source"},
        context={"recovery_context": {"recovery_attempt_id": "context-only"}},
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "execution_authority_denied"
    assert result["runtime_transaction"]["state"] == "blocked"


def test_recovery_apply_requires_transaction() -> None:
    surface = classify_runtime_surface("recovery_apply")

    assert surface.requires_authority is True
    assert surface.requires_transaction is True
    assert surface.mutation is True


def test_recovery_context_alone_is_not_authority(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {"type": "rollback_restore", "rollback_evidence": "backup:file"},
        context={"recovery_context": {"state": "verify_failed"}},
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "execution_authority_denied"


def test_recovery_created_transaction_has_recovery_source(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    source = _source_transaction()
    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {
            "type": "recovery_apply",
            "target_path": "workspace/shared/recovered.txt",
            "original_transaction_id": source.transaction_id,
            "original_trace_id": source.trace_id,
            "recovery_source": "recovery:test",
        },
        context={"execution_authority": _authority("recovery_apply")},
    )

    tx = result["runtime_transaction"]
    assert tx["transaction_id"] != source.transaction_id
    assert tx["recovery_source"] == "recovery:test"
    assert tx["original_transaction_id"] == source.transaction_id


def test_recovery_does_not_overwrite_original_transaction(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    source = _source_transaction("overwrite")
    before = source.to_dict()
    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {
            "type": "recovery_apply",
            "target_path": "workspace/shared/recovered-overwrite.txt",
            "original_transaction_id": source.transaction_id,
            "original_trace_id": source.trace_id,
        },
        context={"execution_authority": _authority("recovery_apply")},
    )

    assert get_transaction(source.transaction_id).to_dict() == before
    assert result["runtime_transaction"]["transaction_id"] != source.transaction_id


def test_verify_failure_cannot_commit(tmp_path: Path) -> None:
    from core.runtime.step_executor import StepExecutor

    source = _source_transaction("verify-fail")
    result = StepExecutor(workspace_root=str(tmp_path)).execute_step(
        {
            "type": "recovery_apply",
            "target_path": "workspace/shared/recovery-fail.txt",
            "original_transaction_id": source.transaction_id,
            "force_verify_fail": True,
        },
        context={"execution_authority": _authority("recovery_apply")},
    )

    assert result["ok"] is False
    assert result["runtime_transaction"]["state"] in {"audited", "failed", "rolled_back"}
    assert "committed" not in result["runtime_transaction"]["state_history"]


def test_rollback_requires_rollback_evidence() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:rollback-source")

    try:
        from core.runtime.runtime_recovery_freeze import record_recovery_rollback

        record_recovery_rollback(attempt, {})
    except ValueError as exc:
        assert "rollback evidence" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("rollback without evidence should fail")


def test_failed_recovery_becomes_failed_terminal() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:failed-source")
    attempt = record_recovery_preflight(attempt, {"ok": True})
    attempt = record_recovery_terminal_failure(attempt, "strategy_exhausted")

    assert attempt.state.value == "failed_terminal"
    assert assert_recovery_terminal_state(attempt) is True


def test_retry_count_is_bounded() -> None:
    attempt = create_recovery_attempt(original_transaction_id="runtime_tx:bounded", max_retries=0)

    assert attempt.retry_count == 0
    assert attempt.max_retries == 0


def test_blocked_recovery_leaves_evidence() -> None:
    evidence = create_recovery_blocked_evidence(
        original_transaction_id="runtime_tx:blocked-source",
        reason="missing_authority",
        trace_id="trace-blocked",
    )

    assert evidence["state"] == "blocked"
    assert evidence["blocked_reason"] == "missing_authority"
    assert evidence["audit_refs"] == ["trace-blocked"]


def _source_transaction(suffix: str = "source"):
    return create_transaction(
        task_id=f"task-{suffix}",
        step_id=f"step-{suffix}",
        trace_id=f"trace-{suffix}",
        authority_source="execution_gateway",
        surface="write_file",
        affected_files=[f"workspace/shared/{suffix}.txt"],
    )


def _authority(surface: str = "recovery_apply") -> dict:
    return {
        "task_id": f"task-{surface}",
        "step_id": f"step-{surface}",
        "authority_source": "execution_gateway",
        "runtime_session": f"session-{surface}",
        "approval_state": "approved",
        "policy_result": {"allowed": True, "decision": "allow"},
        "trace_id": f"trace-{surface}",
    }

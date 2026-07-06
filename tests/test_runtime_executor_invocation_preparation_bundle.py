from pathlib import Path

from core.runtime.runtime_executor_invocation_preparation import (
    ZERO_RUNTIME_EXECUTOR_INVOCATION_PREPARATION_SCHEMA,
    evaluate_executor_invocation_preparation,
    summarize_executor_invocation_preparation,
)


def _attachment() -> dict[str, object]:
    return {
        "adapter_attachment_status": "attached",
        "executor_adapter_attached": True,
        "executor_adapter_attachment_id": "attach-1",
        "executor_adapter_binding_id": "binding-1",
        "executor_envelope_id": "envelope-1",
        "execution_permit_id": "permit-1",
        "execution_admission_id": "admission-1",
        "commit_id": "commit-1",
        "authorization_id": "authorization-1",
        "proposal_id": "proposal-1",
        "decision_id": "decision-1",
        "tick_id": "tick-1",
        "execution_request_id": "request-1",
        "cycle_id": "cycle-1",
        "cycle_binding_id": "cycle-binding-1",
        "worker_id": "worker-1",
        "worker_claim_id": "claim-1",
        "queue_id": "queue-1",
        "queue_entry_id": "queue-entry-1",
        "session_id": "session-1",
        "runtime_session_id": "runtime-session-1",
        "goal_id": "goal-1",
        "work_package_id": "work-package-1",
        "adapter_name": "dry_run_adapter",
        "adapter_metadata": {"mode": "dry_run"},
        "capability_snapshot": {"can_prepare": True, "can_invoke": False},
        "execution_metadata": {"action": "inspect"},
        "executor_invoked": False,
        "execution_started": False,
    }


def test_valid_attachment_prepares_invocation_metadata_only() -> None:
    result = evaluate_executor_invocation_preparation(_attachment())
    assert result["schema"] == ZERO_RUNTIME_EXECUTOR_INVOCATION_PREPARATION_SCHEMA
    assert result["invocation_preparation_status"] == "prepared"
    assert result["executor_invocation_prepared"] is True
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False
    assert result["runtime_mutated"] is False
    assert result["source_executor_adapter_attachment_id"] == "attach-1"
    assert result["executor_adapter_attachment_id"] == "attach-1"
    assert result["denial_reason"] == ""


def test_rejected_attachment_is_rejected() -> None:
    attachment = _attachment()
    attachment["adapter_attachment_status"] = "rejected"
    result = evaluate_executor_invocation_preparation(attachment)
    assert result["invocation_preparation_status"] == "rejected"
    assert result["executor_invocation_prepared"] is False
    assert result["denial_reason"] == "attachment_not_attached"


def test_missing_attachment_is_rejected_deterministically() -> None:
    result = evaluate_executor_invocation_preparation(None)
    assert result["invocation_preparation_status"] == "rejected"
    assert result["denial_reason"] == "missing_executor_adapter_attachment"
    assert result == evaluate_executor_invocation_preparation(None)


def test_duplicate_preparation_is_rejected() -> None:
    first = evaluate_executor_invocation_preparation(_attachment())
    result = evaluate_executor_invocation_preparation(
        _attachment(),
        existing_preparations=[first],
    )
    assert result["invocation_preparation_status"] == "rejected"
    assert result["denial_reason"] == "duplicate_invocation_preparation"
    assert result["executor_invoked"] is False


def test_lineage_is_preserved() -> None:
    result = evaluate_executor_invocation_preparation(_attachment())
    for field in (
        "goal_id",
        "session_id",
        "runtime_session_id",
        "queue_id",
        "queue_entry_id",
        "worker_id",
        "worker_claim_id",
        "cycle_id",
        "cycle_binding_id",
        "execution_request_id",
        "tick_id",
        "decision_id",
        "proposal_id",
        "authorization_id",
        "commit_id",
        "execution_admission_id",
        "execution_permit_id",
        "executor_envelope_id",
        "executor_adapter_binding_id",
        "executor_adapter_attachment_id",
    ):
        assert result[field] == _attachment()[field]


def test_metadata_snapshots_are_preserved() -> None:
    result = evaluate_executor_invocation_preparation(_attachment())
    assert result["adapter_name"] == "dry_run_adapter"
    assert result["adapter_metadata"] == {"mode": "dry_run"}
    assert result["capability_snapshot"] == {"can_prepare": True, "can_invoke": False}
    assert result["execution_metadata"] == {"action": "inspect"}


def test_summary_is_operator_visible_and_safe() -> None:
    result = evaluate_executor_invocation_preparation(_attachment())
    summary = summarize_executor_invocation_preparation(result)
    assert summary["invocation_preparation_status"] == "prepared"
    assert summary["executor_invocation_prepared"] is True
    assert summary["executor_invoked"] is False
    assert summary["execution_started"] is False
    assert summary["executor_invocation_preparation_id"]


def test_source_boundary_has_no_forbidden_execution_surfaces() -> None:
    source = Path("core/runtime/runtime_executor_invocation_preparation.py").read_text(
        encoding="utf-8"
    ).lower()
    forbidden = [
        "subprocess",
        "step_executor",
        "task_runner",
        "agent_loop",
        "progress_memory",
        "scheduler.",
        "from scheduler",
        "import scheduler",
        ".run(",
        "exec(",
        "eval(",
        "open(",
        "write_text",
        "write_bytes",
    ]
    for token in forbidden:
        assert token not in source, f"forbidden token present: {token}"

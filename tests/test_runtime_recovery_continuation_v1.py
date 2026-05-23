from __future__ import annotations

from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_recovery_continuation import (
    CONTINUATION_STATUS_APPLIED,
    CONTINUATION_STATUS_BLOCKED,
    CONTINUATION_STATUS_READY,
    CONTINUATION_STATUS_REQUIRES_REVIEW,
    RuntimeRecoveryContinuationLayer,
    RuntimeRecoveryContinuationPolicy,
)
from core.runtime.runtime_recovery_state import (
    RECOVERY_CONTINUATION_READY,
    RECOVERY_CONTINUATION_REQUIRES_ROLLBACK,
    RECOVERY_EXECUTION_STATUS_BLOCKED,
    RECOVERY_EXECUTION_STATUS_COMPLETED,
)


def build_completed_execution_result():
    return {
        "execution_id": "exec-1",
        "recovery_id": "recovery-1",
        "source_session_id": "session-1",
        "status": RECOVERY_EXECUTION_STATUS_COMPLETED,
        "continuation_decision": RECOVERY_CONTINUATION_READY,
        "verification_snapshot": {"verified": True, "status": "verified"},
        "recovery_chain_status": "verified",
        "source_state_before": {"status": "failed"},
        "source_state_after": {"status": "failed"},
    }


def test_verified_execution_builds_ready_continuation_plan():
    layer = RuntimeRecoveryContinuationLayer()
    plan = layer.plan_continuation(
        build_completed_execution_result(),
        source_state={"status": "failed", "task_id": "task-1"},
        approval={"approved": True},
    )
    payload = plan.to_dict()

    assert payload["status"] == CONTINUATION_STATUS_READY
    assert payload["decision"] == RECOVERY_CONTINUATION_READY
    assert payload["safe_to_apply"] is True
    assert payload["target_runtime_status"] == "running"
    assert any(item["action_type"] == "resume_runtime" for item in payload["actions"])


def test_continuation_does_not_apply_without_approval_by_default():
    layer = RuntimeRecoveryContinuationLayer()
    plan = layer.plan_continuation(
        build_completed_execution_result(),
        source_state={"status": "failed"},
    )

    result = layer.apply_continuation(plan, source_state={"status": "failed"})
    payload = result.to_dict()

    assert payload["status"] == CONTINUATION_STATUS_REQUIRES_REVIEW
    assert payload["applied"] is False
    assert payload["source_state_mutated"] is False
    assert payload["source_state_after"]["status"] == "failed"


def test_continuation_applies_only_with_explicit_approval():
    layer = RuntimeRecoveryContinuationLayer()
    plan = layer.plan_continuation(
        build_completed_execution_result(),
        source_state={"status": "failed", "task_id": "task-1"},
        approval={"approved": True},
    )

    result = layer.apply_continuation(
        plan,
        source_state={"status": "failed", "task_id": "task-1"},
        approval={"approved": True},
    )
    payload = result.to_dict()

    assert payload["status"] == CONTINUATION_STATUS_APPLIED
    assert payload["applied"] is True
    assert payload["source_state_mutated"] is True
    assert payload["source_state_after"]["status"] == "running"
    assert payload["source_state_after"]["runtime_recovery_continuation"]["recovery_id"] == "recovery-1"


def test_rollback_required_blocks_runtime_continuation():
    layer = RuntimeRecoveryContinuationLayer()
    execution = build_completed_execution_result()
    execution["continuation_decision"] = RECOVERY_CONTINUATION_REQUIRES_ROLLBACK
    execution["recovery_chain_status"] = "rollback_required"

    plan = layer.plan_continuation(
        execution,
        source_state={"status": "failed"},
        approval={"approved": True},
    )
    result = layer.apply_continuation(plan, source_state={"status": "failed"}, approval={"approved": True})

    assert plan.to_dict()["status"] == CONTINUATION_STATUS_BLOCKED
    assert plan.to_dict()["requires_rollback"] is True
    assert result.to_dict()["applied"] is False
    assert result.to_dict()["source_state_after"]["status"] == "failed"


def test_blocked_execution_blocks_continuation_even_if_approved():
    layer = RuntimeRecoveryContinuationLayer()
    execution = build_completed_execution_result()
    execution["status"] = RECOVERY_EXECUTION_STATUS_BLOCKED

    plan = layer.plan_continuation(
        execution,
        source_state={"status": "failed"},
        approval={"approved": True},
    )

    assert plan.to_dict()["status"] == CONTINUATION_STATUS_BLOCKED
    assert plan.to_dict()["safe_to_apply"] is False
    assert plan.to_dict()["requires_review"] is True


def test_custom_continuation_handler_receives_controlled_surface():
    def handler(plan, context):
        state = dict(context["source_state"])
        state["status"] = "running"
        state["continued_by"] = plan["continuation_id"]
        return {"ok": True, "mode": "custom_handler", "source_state": state}

    layer = RuntimeRecoveryContinuationLayer(handler=handler)
    plan = layer.plan_continuation(
        build_completed_execution_result(),
        source_state={"status": "failed"},
        approval={"approved": True},
    )
    result = layer.apply_continuation(plan, source_state={"status": "failed"}, approval={"approved": True})

    payload = result.to_dict()
    assert payload["status"] == CONTINUATION_STATUS_APPLIED
    assert payload["source_state_after"]["continued_by"] == plan.continuation_id
    assert payload["action_results"][0]["mode"] == "custom_handler"


def test_continuation_layer_writes_journal_records():
    journal = RuntimeJournal()
    layer = RuntimeRecoveryContinuationLayer(journal=journal)
    plan = layer.plan_continuation(
        build_completed_execution_result(),
        source_state={"status": "failed"},
        approval={"approved": True},
    )
    layer.apply_continuation(plan, source_state={"status": "failed"}, approval={"approved": True})

    reconstruction = journal.reconstruct()
    record_types = [item["record_type"] for item in reconstruction["records"]]
    assert "runtime_recovery_continuation_plan" in record_types
    assert "runtime_recovery_continuation_result" in record_types
    assert "runtime_recovery_continuation_audit_event" in record_types

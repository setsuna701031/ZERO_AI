from __future__ import annotations

import pytest

from core.runtime.runtime_queue_finalization_contract import build_queue_finalization_request
from core.runtime.runtime_queue_finalization_policy import evaluate_queue_finalization_policy
from core.runtime.runtime_queue_finalization_preview import prepare_runtime_queue_finalization_preview


def _payload(**overrides):
    payload = {
        "task_id": "task-1081",
        "queue_item_id": "queue-item-1081",
        "lifecycle_status": "finished",
        "result_commit_status": "committed",
        "runtime_state_update_status": "updated",
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def test_queue_finalization_request_requires_identity_and_status_fields():
    request = build_queue_finalization_request(_payload())

    assert request.task_id == "task-1081"
    assert request.queue_item_id == "queue-item-1081"
    assert request.lifecycle_status == "finished"
    assert request.result_commit_status == "committed"
    assert request.runtime_state_update_status == "updated"


@pytest.mark.parametrize(
    "missing_field",
    [
        "task_id",
        "queue_item_id",
        "lifecycle_status",
        "result_commit_status",
        "runtime_state_update_status",
    ],
)
def test_queue_finalization_request_rejects_missing_required_fields(missing_field):
    payload = _payload()
    payload[missing_field] = ""

    with pytest.raises(ValueError):
        build_queue_finalization_request(payload)


def test_queue_finalization_policy_is_disabled_even_when_finalizable():
    request = build_queue_finalization_request(_payload())
    result = evaluate_queue_finalization_policy(request)

    assert result["enabled"] is False
    assert result["preview_only"] is True
    assert result["finalizable_preview"] is True
    assert result["queue_finalization_allowed"] is False
    assert result["queue_mutation_allowed"] is False
    assert result["runtime_state_mutation_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["autonomous_execution_allowed"] is False
    assert result["blockers"] == []


def test_queue_finalization_policy_reports_blockers_without_mutation_authority():
    request = build_queue_finalization_request(
        _payload(
            lifecycle_status="running",
            result_commit_status="pending",
            runtime_state_update_status="pending",
        )
    )
    result = evaluate_queue_finalization_policy(request)

    assert result["finalizable_preview"] is False
    assert "lifecycle_status_not_finalizable" in result["blockers"]
    assert "result_commit_not_ready" in result["blockers"]
    assert "runtime_state_update_not_ready" in result["blockers"]
    assert result["queue_finalization_allowed"] is False


def test_prepare_runtime_queue_finalization_preview_is_pure_disabled_bundle():
    result = prepare_runtime_queue_finalization_preview(_payload())

    assert result["enabled"] is False
    assert result["preview_only"] is True
    assert result["queue_finalization_allowed"] is False
    assert result["queue_mutation_performed"] is False
    assert result["runtime_state_mutation_performed"] is False
    assert result["tool_execution_performed"] is False
    assert result["autonomous_execution_performed"] is False

    assert result["policy_result"]["finalizable_preview"] is True
    assert result["projection"]["projected_queue_status"] == "finalization_preview_reserved"
    assert result["audit_record"]["decision"] == "reserved_no_mutation"


def test_queue_finalization_preview_preserves_no_real_execution_boundary():
    result = prepare_runtime_queue_finalization_preview(_payload())

    forbidden_flags = [
        result["policy_result"]["queue_mutation_allowed"],
        result["policy_result"]["runtime_state_mutation_allowed"],
        result["policy_result"]["tool_execution_allowed"],
        result["policy_result"]["autonomous_execution_allowed"],
        result["projection"]["queue_mutation_performed"],
        result["projection"]["runtime_state_mutation_performed"],
        result["projection"]["tool_execution_performed"],
        result["projection"]["autonomous_execution_performed"],
        result["audit_record"]["queue_mutation_performed"],
        result["audit_record"]["runtime_state_mutation_performed"],
        result["audit_record"]["tool_execution_performed"],
        result["audit_record"]["autonomous_execution_performed"],
    ]

    assert forbidden_flags == [False] * len(forbidden_flags)

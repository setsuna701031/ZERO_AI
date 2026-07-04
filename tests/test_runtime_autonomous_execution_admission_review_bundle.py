from __future__ import annotations

import pytest

from core.runtime.runtime_autonomous_execution_admission_contract import (
    build_autonomous_execution_admission_request,
)
from core.runtime.runtime_autonomous_execution_admission_policy import (
    evaluate_autonomous_execution_admission,
)
from core.runtime.runtime_autonomous_execution_admission_review import (
    prepare_runtime_autonomous_execution_admission_review,
)


def _payload(**overrides):
    payload = {
        "request_id": "autonomous-request-1105",
        "task_id": "task-1105",
        "trigger_source": "operator_explicit_start",
        "operator_override": True,
        "execution_budget": {"max_steps": 3, "max_seconds": 30},
        "stop_condition": "stop_when_queue_empty_or_budget_exhausted",
        "self_loop_guard": True,
        "audit_required": True,
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def test_autonomous_execution_request_requires_identity_trigger_safety_and_audit():
    request = build_autonomous_execution_admission_request(_payload())

    assert request.request_id == "autonomous-request-1105"
    assert request.task_id == "task-1105"
    assert request.trigger_source == "operator_explicit_start"
    assert request.operator_override is True
    assert request.execution_budget == {"max_steps": 3, "max_seconds": 30}
    assert request.stop_condition == "stop_when_queue_empty_or_budget_exhausted"
    assert request.self_loop_guard is True
    assert request.audit_required is True


@pytest.mark.parametrize(
    "missing_field",
    [
        "request_id",
        "task_id",
        "trigger_source",
        "stop_condition",
    ],
)
def test_autonomous_execution_request_rejects_missing_string_fields(missing_field):
    payload = _payload()
    payload[missing_field] = ""

    with pytest.raises(ValueError):
        build_autonomous_execution_admission_request(payload)


@pytest.mark.parametrize(
    "missing_field",
    [
        "operator_override",
        "execution_budget",
        "self_loop_guard",
        "audit_required",
    ],
)
def test_autonomous_execution_request_rejects_missing_boolean_or_object_fields(missing_field):
    payload = _payload()
    payload.pop(missing_field)

    with pytest.raises(ValueError):
        build_autonomous_execution_admission_request(payload)


def test_autonomous_execution_request_rejects_non_mapping_budget():
    with pytest.raises(ValueError):
        build_autonomous_execution_admission_request(
            _payload(execution_budget="not-a-mapping")
        )


def test_autonomous_execution_policy_can_be_ready_in_preview_but_never_starts_loop():
    request = build_autonomous_execution_admission_request(_payload())
    result = evaluate_autonomous_execution_admission(request)

    assert result["enabled"] is False
    assert result["review_only"] is True
    assert result["preview_only"] is True
    assert result["autonomous_execution_admission_ready_preview"] is True
    assert result["autonomous_execution_allowed"] is False
    assert result["autonomous_loop_start_allowed"] is False
    assert result["new_task_dispatch_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["queue_mutation_allowed"] is False
    assert result["external_io_allowed"] is False
    assert result["blockers"] == []


def test_autonomous_execution_policy_reports_all_safety_blockers():
    request = build_autonomous_execution_admission_request(
        _payload(
            trigger_source="untrusted",
            operator_override=False,
            execution_budget={"max_steps": 0, "max_seconds": 0},
            stop_condition="",
            self_loop_guard=False,
            audit_required=False,
        )
    )
    result = evaluate_autonomous_execution_admission(request)

    assert result["autonomous_execution_admission_ready_preview"] is False
    assert "untrusted_trigger_source" in result["blockers"]
    assert "operator_override_missing" in result["blockers"]
    assert "max_steps_budget_missing" in result["blockers"]
    assert "max_seconds_budget_missing" in result["blockers"]
    assert "stop_condition_missing" in result["blockers"]
    assert "self_loop_guard_missing" in result["blockers"]
    assert "audit_not_required" in result["blockers"]
    assert result["autonomous_execution_allowed"] is False


def test_prepare_autonomous_execution_admission_review_is_disabled_bundle():
    result = prepare_runtime_autonomous_execution_admission_review(_payload())

    assert result["enabled"] is False
    assert result["review_only"] is True
    assert result["preview_only"] is True
    assert result["autonomous_execution_allowed"] is False
    assert result["autonomous_loop_started"] is False
    assert result["new_task_dispatched"] is False
    assert result["tool_execution_performed"] is False
    assert result["runtime_mutation_performed"] is False
    assert result["queue_mutation_performed"] is False
    assert result["external_io_performed"] is False

    assert result["policy_result"]["autonomous_execution_admission_ready_preview"] is True
    assert (
        result["projection"]["projected_admission_status"]
        == "autonomous_execution_admission_review_reserved"
    )
    assert result["audit_record"]["decision"] == "reserved_no_autonomous_execution"


def test_autonomous_execution_admission_review_preserves_no_effect_boundary():
    result = prepare_runtime_autonomous_execution_admission_review(_payload())

    forbidden_flags = [
        result["policy_result"]["autonomous_execution_allowed"],
        result["policy_result"]["autonomous_loop_start_allowed"],
        result["policy_result"]["new_task_dispatch_allowed"],
        result["policy_result"]["tool_execution_allowed"],
        result["policy_result"]["runtime_mutation_allowed"],
        result["policy_result"]["queue_mutation_allowed"],
        result["policy_result"]["external_io_allowed"],
        result["projection"]["autonomous_loop_started"],
        result["projection"]["new_task_dispatched"],
        result["projection"]["tool_execution_performed"],
        result["projection"]["runtime_mutation_performed"],
        result["projection"]["queue_mutation_performed"],
        result["projection"]["external_io_performed"],
        result["audit_record"]["autonomous_loop_started"],
        result["audit_record"]["new_task_dispatched"],
        result["audit_record"]["tool_execution_performed"],
        result["audit_record"]["runtime_mutation_performed"],
        result["audit_record"]["queue_mutation_performed"],
        result["audit_record"]["external_io_performed"],
    ]

    assert forbidden_flags == [False] * len(forbidden_flags)

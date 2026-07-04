from __future__ import annotations

import pytest

from core.runtime.runtime_real_tool_execution_admission_contract import (
    build_real_tool_execution_admission_request,
)
from core.runtime.runtime_real_tool_execution_admission_policy import (
    evaluate_real_tool_execution_admission,
)
from core.runtime.runtime_real_tool_execution_admission_review import (
    prepare_runtime_real_tool_execution_admission_review,
)


def _payload(**overrides):
    payload = {
        "request_id": "tool-request-1097",
        "task_id": "task-1097",
        "tool_name": "workspace_writer",
        "capability_scope": "workspace_write_preview",
        "side_effect_class": "workspace_preview",
        "executor_authority": "executor_admission_gate",
        "audit_required": True,
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def test_real_tool_execution_request_requires_identity_tool_scope_authority_and_audit():
    request = build_real_tool_execution_admission_request(_payload())

    assert request.request_id == "tool-request-1097"
    assert request.task_id == "task-1097"
    assert request.tool_name == "workspace_writer"
    assert request.capability_scope == "workspace_write_preview"
    assert request.side_effect_class == "workspace_preview"
    assert request.executor_authority == "executor_admission_gate"
    assert request.audit_required is True


@pytest.mark.parametrize(
    "missing_field",
    [
        "request_id",
        "task_id",
        "tool_name",
        "capability_scope",
        "side_effect_class",
        "executor_authority",
    ],
)
def test_real_tool_execution_request_rejects_missing_string_fields(missing_field):
    payload = _payload()
    payload[missing_field] = ""

    with pytest.raises(ValueError):
        build_real_tool_execution_admission_request(payload)


def test_real_tool_execution_request_rejects_missing_audit_field():
    payload = _payload()
    payload.pop("audit_required")

    with pytest.raises(ValueError):
        build_real_tool_execution_admission_request(payload)


def test_real_tool_execution_policy_can_be_ready_in_preview_but_never_invokes_tool():
    request = build_real_tool_execution_admission_request(_payload())
    result = evaluate_real_tool_execution_admission(request)

    assert result["enabled"] is False
    assert result["review_only"] is True
    assert result["preview_only"] is True
    assert result["real_tool_execution_admission_ready_preview"] is True
    assert result["real_tool_execution_allowed"] is False
    assert result["tool_invocation_allowed"] is False
    assert result["tool_side_effect_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["queue_mutation_allowed"] is False
    assert result["external_io_allowed"] is False
    assert result["autonomous_execution_allowed"] is False
    assert result["blockers"] == []


def test_real_tool_execution_policy_reports_blockers():
    request = build_real_tool_execution_admission_request(
        _payload(
            capability_scope="unknown",
            side_effect_class="unknown",
            executor_authority="untrusted",
            audit_required=False,
        )
    )
    result = evaluate_real_tool_execution_admission(request)

    assert result["real_tool_execution_admission_ready_preview"] is False
    assert "unknown_capability_scope" in result["blockers"]
    assert "unknown_side_effect_class" in result["blockers"]
    assert "untrusted_executor_authority" in result["blockers"]
    assert "audit_not_required" in result["blockers"]
    assert result["real_tool_execution_allowed"] is False


def test_real_tool_execution_policy_blocks_runtime_side_effect_without_mutation_admission():
    request = build_real_tool_execution_admission_request(
        _payload(
            capability_scope="workspace_write_preview",
            side_effect_class="runtime_admitted",
        )
    )
    result = evaluate_real_tool_execution_admission(request)

    assert result["real_tool_execution_admission_ready_preview"] is False
    assert "runtime_side_effect_without_runtime_mutation_admission" in result["blockers"]
    assert result["real_tool_execution_allowed"] is False


def test_prepare_real_tool_execution_admission_review_is_disabled_bundle():
    result = prepare_runtime_real_tool_execution_admission_review(_payload())

    assert result["enabled"] is False
    assert result["review_only"] is True
    assert result["preview_only"] is True
    assert result["real_tool_execution_allowed"] is False
    assert result["tool_invocation_performed"] is False
    assert result["tool_side_effect_performed"] is False
    assert result["runtime_mutation_performed"] is False
    assert result["queue_mutation_performed"] is False
    assert result["external_io_performed"] is False
    assert result["autonomous_execution_performed"] is False

    assert result["policy_result"]["real_tool_execution_admission_ready_preview"] is True
    assert (
        result["projection"]["projected_admission_status"]
        == "real_tool_execution_admission_review_reserved"
    )
    assert result["audit_record"]["decision"] == "reserved_no_real_tool_execution"


def test_real_tool_execution_admission_review_preserves_no_effect_boundary():
    result = prepare_runtime_real_tool_execution_admission_review(_payload())

    forbidden_flags = [
        result["policy_result"]["real_tool_execution_allowed"],
        result["policy_result"]["tool_invocation_allowed"],
        result["policy_result"]["tool_side_effect_allowed"],
        result["policy_result"]["runtime_mutation_allowed"],
        result["policy_result"]["queue_mutation_allowed"],
        result["policy_result"]["external_io_allowed"],
        result["policy_result"]["autonomous_execution_allowed"],
        result["projection"]["tool_invocation_performed"],
        result["projection"]["tool_side_effect_performed"],
        result["projection"]["runtime_mutation_performed"],
        result["projection"]["queue_mutation_performed"],
        result["projection"]["external_io_performed"],
        result["projection"]["autonomous_execution_performed"],
        result["audit_record"]["tool_invocation_performed"],
        result["audit_record"]["tool_side_effect_performed"],
        result["audit_record"]["runtime_mutation_performed"],
        result["audit_record"]["queue_mutation_performed"],
        result["audit_record"]["external_io_performed"],
        result["audit_record"]["autonomous_execution_performed"],
    ]

    assert forbidden_flags == [False] * len(forbidden_flags)

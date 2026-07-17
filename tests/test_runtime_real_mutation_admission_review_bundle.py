from __future__ import annotations

import pytest

from core.runtime.runtime_real_mutation_admission_contract import (
    build_real_mutation_admission_request,
)
from core.runtime.runtime_real_mutation_admission_policy import (
    evaluate_real_mutation_admission,
)
from core.runtime.runtime_real_mutation_admission_review import (
    prepare_runtime_real_mutation_admission_review,
)


def _payload(**overrides):
    payload = {
        "request_id": "mutation-request-1089",
        "task_id": "task-1089",
        "mutation_type": "runtime_state_update",
        "target_scope": "runtime_state",
        "authority_source": "runtime_activation_gate",
        "audit_required": True,
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def test_real_mutation_admission_request_requires_identity_authority_and_audit():
    request = build_real_mutation_admission_request(_payload())

    assert request.request_id == "mutation-request-1089"
    assert request.task_id == "task-1089"
    assert request.mutation_type == "runtime_state_update"
    assert request.target_scope == "runtime_state"
    assert request.authority_source == "runtime_activation_gate"
    assert request.audit_required is True


@pytest.mark.parametrize(
    "missing_field",
    [
        "request_id",
        "task_id",
        "mutation_type",
        "target_scope",
        "authority_source",
    ],
)
def test_real_mutation_admission_request_rejects_missing_string_fields(missing_field):
    payload = _payload()
    payload[missing_field] = ""

    with pytest.raises(ValueError):
        build_real_mutation_admission_request(payload)


def test_real_mutation_admission_request_rejects_missing_audit_field():
    payload = _payload()
    payload.pop("audit_required")

    with pytest.raises(ValueError):
        build_real_mutation_admission_request(payload)


def test_real_mutation_policy_can_be_ready_in_preview_but_never_allows_mutation():
    request = build_real_mutation_admission_request(_payload())
    result = evaluate_real_mutation_admission(request)

    assert result["enabled"] is False
    assert result["review_only"] is True
    assert result["preview_only"] is True
    assert result["real_mutation_admission_ready_preview"] is True
    assert result["real_mutation_allowed"] is False
    assert result["runtime_state_mutation_allowed"] is False
    assert result["queue_mutation_allowed"] is False
    assert result["task_lifecycle_mutation_allowed"] is False
    assert result["result_store_mutation_allowed"] is False
    assert result["tool_execution_allowed"] is False
    assert result["autonomous_execution_allowed"] is False
    assert result["blockers"] == []


def test_real_mutation_policy_reports_blockers():
    request = build_real_mutation_admission_request(
        _payload(
            mutation_type="unknown",
            target_scope="unknown",
            authority_source="untrusted",
            audit_required=False,
        )
    )
    result = evaluate_real_mutation_admission(request)

    assert result["real_mutation_admission_ready_preview"] is False
    assert "unknown_mutation_type" in result["blockers"]
    assert "unknown_target_scope" in result["blockers"]
    assert "untrusted_authority_source" in result["blockers"]
    assert "audit_not_required" in result["blockers"]
    assert result["real_mutation_allowed"] is False


def test_prepare_real_mutation_admission_review_is_disabled_bundle():
    result = prepare_runtime_real_mutation_admission_review(_payload())

    assert result["enabled"] is False
    assert result["review_only"] is True
    assert result["preview_only"] is True
    assert result["real_mutation_allowed"] is False
    assert result["runtime_state_mutation_performed"] is False
    assert result["queue_mutation_performed"] is False
    assert result["task_lifecycle_mutation_performed"] is False
    assert result["result_store_mutation_performed"] is False
    assert result["tool_execution_performed"] is False
    assert result["autonomous_execution_performed"] is False

    assert result["policy_result"]["real_mutation_admission_ready_preview"] is True
    assert result["projection"]["projected_admission_status"] == "real_mutation_admission_review_reserved"
    assert result["audit_record"]["decision"] == "reserved_no_real_mutation"


def test_real_mutation_admission_review_preserves_no_effect_boundary():
    result = prepare_runtime_real_mutation_admission_review(_payload())

    forbidden_flags = [
        result["policy_result"]["real_mutation_allowed"],
        result["policy_result"]["runtime_state_mutation_allowed"],
        result["policy_result"]["queue_mutation_allowed"],
        result["policy_result"]["task_lifecycle_mutation_allowed"],
        result["policy_result"]["result_store_mutation_allowed"],
        result["policy_result"]["tool_execution_allowed"],
        result["policy_result"]["autonomous_execution_allowed"],
        result["projection"]["runtime_state_mutation_performed"],
        result["projection"]["queue_mutation_performed"],
        result["projection"]["task_lifecycle_mutation_performed"],
        result["projection"]["result_store_mutation_performed"],
        result["projection"]["tool_execution_performed"],
        result["projection"]["autonomous_execution_performed"],
        result["audit_record"]["runtime_state_mutation_performed"],
        result["audit_record"]["queue_mutation_performed"],
        result["audit_record"]["task_lifecycle_mutation_performed"],
        result["audit_record"]["result_store_mutation_performed"],
        result["audit_record"]["tool_execution_performed"],
        result["audit_record"]["autonomous_execution_performed"],
    ]

    assert forbidden_flags == [False] * len(forbidden_flags)

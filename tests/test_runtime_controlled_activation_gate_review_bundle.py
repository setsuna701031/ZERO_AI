from __future__ import annotations

import pytest

from core.runtime.runtime_controlled_activation_gate_contract import (
    build_controlled_activation_gate_review_request,
)
from core.runtime.runtime_controlled_activation_gate_policy import (
    evaluate_controlled_activation_gate,
)
from core.runtime.runtime_controlled_activation_gate_review import (
    prepare_controlled_activation_gate_review,
)


def _payload(**overrides):
    payload = {
        "gate_request_id": "gate-1129",
        "activation_attempt_id": "activation-attempt-1129",
        "transition_id": "transition-1129",
        "operator_id": "operator-1129",
        "dry_run_result": {
            "dry_run_ready_preview": True,
            "controlled_activation_allowed": False,
        },
        "mode_authority": {
            "verified": True,
            "target_mode": "controlled_active_candidate",
        },
        "activation_token": {
            "valid": True,
            "token_id": "activation-token-1129",
        },
        "activation_lease": {
            "bounded": True,
            "ttl_seconds": 60,
        },
        "controlled_active_boundary": {
            "real_mutation_enabled": False,
            "real_tool_execution_enabled": False,
            "autonomous_execution_enabled": False,
            "external_io_enabled": False,
        },
        "rollback_authority": {
            "verified": True,
        },
        "kill_switch_authority": {
            "verified": True,
        },
        "audit_required": True,
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def test_controlled_activation_gate_request_requires_identity_and_authority_surfaces():
    request = build_controlled_activation_gate_review_request(_payload())

    assert request.gate_request_id == "gate-1129"
    assert request.activation_attempt_id == "activation-attempt-1129"
    assert request.transition_id == "transition-1129"
    assert request.operator_id == "operator-1129"
    assert request.audit_required is True


@pytest.mark.parametrize(
    "missing_field",
    [
        "gate_request_id",
        "activation_attempt_id",
        "transition_id",
        "operator_id",
    ],
)
def test_controlled_activation_gate_request_rejects_missing_string_fields(missing_field):
    payload = _payload()
    payload[missing_field] = ""

    with pytest.raises(ValueError):
        build_controlled_activation_gate_review_request(payload)


@pytest.mark.parametrize(
    "missing_field",
    [
        "dry_run_result",
        "mode_authority",
        "activation_token",
        "activation_lease",
        "controlled_active_boundary",
        "rollback_authority",
        "kill_switch_authority",
        "audit_required",
    ],
)
def test_controlled_activation_gate_request_rejects_missing_review_fields(missing_field):
    payload = _payload()
    payload.pop(missing_field)

    with pytest.raises(ValueError):
        build_controlled_activation_gate_review_request(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "dry_run_result",
        "mode_authority",
        "activation_token",
        "activation_lease",
        "controlled_active_boundary",
        "rollback_authority",
        "kill_switch_authority",
    ],
)
def test_controlled_activation_gate_request_rejects_non_mapping_review_fields(field_name):
    payload = _payload()
    payload[field_name] = "not-a-mapping"

    with pytest.raises(ValueError):
        build_controlled_activation_gate_review_request(payload)


def test_controlled_activation_gate_can_be_ready_in_preview_but_never_opens():
    request = build_controlled_activation_gate_review_request(_payload())
    result = evaluate_controlled_activation_gate(request)

    assert result["enabled"] is False
    assert result["gate_review_only"] is True
    assert result["preview_only"] is True
    assert result["controlled_activation_gate_ready_preview"] is True
    assert result["controlled_activation_allowed"] is False
    assert result["runtime_mode_transition_allowed"] is False
    assert result["controlled_active_enabled"] is False
    assert result["real_mutation_enabled"] is False
    assert result["real_tool_execution_enabled"] is False
    assert result["autonomous_execution_enabled"] is False
    assert result["new_task_dispatch_allowed"] is False
    assert result["tool_invocation_allowed"] is False
    assert result["external_io_allowed"] is False
    assert result["blockers"] == []


def test_controlled_activation_gate_blocks_bad_dry_run_and_authority():
    request = build_controlled_activation_gate_review_request(
        _payload(
            dry_run_result={
                "dry_run_ready_preview": False,
                "controlled_activation_allowed": True,
            },
            mode_authority={
                "verified": False,
                "target_mode": "unsupported",
            },
        )
    )
    result = evaluate_controlled_activation_gate(request)

    assert result["controlled_activation_gate_ready_preview"] is False
    assert "dry_run_not_ready" in result["blockers"]
    assert "dry_run_attempted_real_activation" in result["blockers"]
    assert "mode_authority_not_verified" in result["blockers"]
    assert "unsupported_controlled_target_mode" in result["blockers"]


def test_controlled_activation_gate_blocks_bad_token_and_lease():
    request = build_controlled_activation_gate_review_request(
        _payload(
            activation_token={"valid": False, "token_id": ""},
            activation_lease={"bounded": False, "ttl_seconds": 0},
        )
    )
    result = evaluate_controlled_activation_gate(request)

    assert result["controlled_activation_gate_ready_preview"] is False
    assert "activation_token_invalid" in result["blockers"]
    assert "activation_token_missing_id" in result["blockers"]
    assert "activation_lease_unbounded" in result["blockers"]
    assert "activation_lease_ttl_missing" in result["blockers"]


def test_controlled_activation_gate_blocks_boundary_unlocks():
    request = build_controlled_activation_gate_review_request(
        _payload(
            controlled_active_boundary={
                "real_mutation_enabled": True,
                "real_tool_execution_enabled": True,
                "autonomous_execution_enabled": True,
                "external_io_enabled": True,
            }
        )
    )
    result = evaluate_controlled_activation_gate(request)

    assert result["controlled_activation_gate_ready_preview"] is False
    assert "boundary_real_mutation_not_locked" in result["blockers"]
    assert "boundary_real_tool_execution_not_locked" in result["blockers"]
    assert "boundary_autonomous_execution_not_locked" in result["blockers"]
    assert "boundary_external_io_not_locked" in result["blockers"]


def test_controlled_activation_gate_blocks_missing_rollback_kill_switch_and_audit():
    request = build_controlled_activation_gate_review_request(
        _payload(
            rollback_authority={"verified": False},
            kill_switch_authority={"verified": False},
            audit_required=False,
        )
    )
    result = evaluate_controlled_activation_gate(request)

    assert result["controlled_activation_gate_ready_preview"] is False
    assert "rollback_authority_not_verified" in result["blockers"]
    assert "kill_switch_authority_not_verified" in result["blockers"]
    assert "audit_not_required" in result["blockers"]


def test_prepare_controlled_activation_gate_review_is_disabled_bundle():
    result = prepare_controlled_activation_gate_review(_payload())

    assert result["enabled"] is False
    assert result["gate_review_only"] is True
    assert result["preview_only"] is True
    assert result["controlled_activation_allowed"] is False
    assert result["runtime_mode_transition_performed"] is False
    assert result["controlled_active_enabled"] is False
    assert result["real_mutation_enabled"] is False
    assert result["real_tool_execution_enabled"] is False
    assert result["autonomous_execution_enabled"] is False
    assert result["new_task_dispatched"] is False
    assert result["tool_invoked"] is False
    assert result["external_io_performed"] is False

    assert result["policy_result"]["controlled_activation_gate_ready_preview"] is True
    assert (
        result["projection"]["projected_gate_status"]
        == "controlled_activation_gate_review_reserved"
    )
    assert result["audit_record"]["decision"] == "reserved_no_controlled_activation_gate_open"


def test_controlled_activation_gate_review_preserves_no_effect_boundary():
    result = prepare_controlled_activation_gate_review(_payload())

    forbidden_flags = [
        result["controlled_activation_allowed"],
        result["runtime_mode_transition_performed"],
        result["controlled_active_enabled"],
        result["real_mutation_enabled"],
        result["real_tool_execution_enabled"],
        result["autonomous_execution_enabled"],
        result["new_task_dispatched"],
        result["tool_invoked"],
        result["external_io_performed"],
        result["policy_result"]["controlled_activation_allowed"],
        result["policy_result"]["runtime_mode_transition_allowed"],
        result["policy_result"]["controlled_active_enabled"],
        result["policy_result"]["real_mutation_enabled"],
        result["policy_result"]["real_tool_execution_enabled"],
        result["policy_result"]["autonomous_execution_enabled"],
        result["policy_result"]["new_task_dispatch_allowed"],
        result["policy_result"]["tool_invocation_allowed"],
        result["policy_result"]["external_io_allowed"],
        result["projection"]["controlled_activation_allowed"],
        result["projection"]["runtime_mode_transition_performed"],
        result["projection"]["controlled_active_enabled"],
        result["projection"]["real_mutation_enabled"],
        result["projection"]["real_tool_execution_enabled"],
        result["projection"]["autonomous_execution_enabled"],
        result["projection"]["new_task_dispatched"],
        result["projection"]["tool_invoked"],
        result["projection"]["external_io_performed"],
        result["audit_record"]["controlled_activation_allowed"],
        result["audit_record"]["runtime_mode_transition_performed"],
        result["audit_record"]["controlled_active_enabled"],
        result["audit_record"]["real_mutation_enabled"],
        result["audit_record"]["real_tool_execution_enabled"],
        result["audit_record"]["autonomous_execution_enabled"],
        result["audit_record"]["new_task_dispatched"],
        result["audit_record"]["tool_invoked"],
        result["audit_record"]["external_io_performed"],
    ]

    assert forbidden_flags == [False] * len(forbidden_flags)

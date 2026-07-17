from __future__ import annotations

import pytest

from core.runtime.runtime_controlled_active_limited_mode_candidate import (
    prepare_controlled_active_limited_mode_candidate,
)
from core.runtime.runtime_controlled_active_limited_mode_contract import (
    build_controlled_active_limited_mode_candidate,
)
from core.runtime.runtime_controlled_active_limited_mode_policy import (
    evaluate_controlled_active_limited_mode_candidate,
)


def _payload(**overrides):
    payload = {
        "candidate_id": "limited-candidate-1137",
        "activation_attempt_id": "activation-attempt-1137",
        "operator_id": "operator-1137",
        "source_mode": "disabled",
        "candidate_mode": "controlled_active_limited",
        "gate_review_result": {
            "controlled_activation_gate_ready_preview": True,
            "controlled_activation_allowed": False,
        },
        "limited_scheduler": {
            "enabled_preview": True,
            "unbounded_loop": False,
        },
        "internal_execution_boundary": {
            "internal_execution_allowed_preview": True,
            "external_execution_allowed": False,
        },
        "state_transition_boundary": {
            "state_transition_allowed_preview": True,
            "real_runtime_state_mutation": False,
        },
        "mutation_boundary": {
            "real_file_mutation_allowed": False,
            "runtime_mutation_allowed": False,
        },
        "tool_boundary": {
            "external_tool_execution_allowed": False,
            "network_io_allowed": False,
        },
        "autonomy_boundary": {
            "unbounded_autonomy_allowed": False,
            "self_start_allowed": False,
        },
        "audit_required": True,
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def test_controlled_active_limited_candidate_requires_identity_and_boundaries():
    candidate = build_controlled_active_limited_mode_candidate(_payload())

    assert candidate.candidate_id == "limited-candidate-1137"
    assert candidate.activation_attempt_id == "activation-attempt-1137"
    assert candidate.operator_id == "operator-1137"
    assert candidate.source_mode == "disabled"
    assert candidate.candidate_mode == "controlled_active_limited"
    assert candidate.audit_required is True


@pytest.mark.parametrize(
    "missing_field",
    [
        "candidate_id",
        "activation_attempt_id",
        "operator_id",
        "source_mode",
        "candidate_mode",
    ],
)
def test_controlled_active_limited_candidate_rejects_missing_string_fields(missing_field):
    payload = _payload()
    payload[missing_field] = ""

    with pytest.raises(ValueError):
        build_controlled_active_limited_mode_candidate(payload)


@pytest.mark.parametrize(
    "missing_field",
    [
        "gate_review_result",
        "limited_scheduler",
        "internal_execution_boundary",
        "state_transition_boundary",
        "mutation_boundary",
        "tool_boundary",
        "autonomy_boundary",
        "audit_required",
    ],
)
def test_controlled_active_limited_candidate_rejects_missing_boundary_fields(missing_field):
    payload = _payload()
    payload.pop(missing_field)

    with pytest.raises(ValueError):
        build_controlled_active_limited_mode_candidate(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "gate_review_result",
        "limited_scheduler",
        "internal_execution_boundary",
        "state_transition_boundary",
        "mutation_boundary",
        "tool_boundary",
        "autonomy_boundary",
    ],
)
def test_controlled_active_limited_candidate_rejects_non_mapping_boundaries(field_name):
    payload = _payload()
    payload[field_name] = "not-a-mapping"

    with pytest.raises(ValueError):
        build_controlled_active_limited_mode_candidate(payload)


def test_controlled_active_limited_candidate_can_be_ready_in_preview_but_never_enables_mode():
    candidate = build_controlled_active_limited_mode_candidate(_payload())
    result = evaluate_controlled_active_limited_mode_candidate(candidate)

    assert result["enabled"] is False
    assert result["candidate_only"] is True
    assert result["preview_only"] is True
    assert result["controlled_active_limited_candidate_ready_preview"] is True
    assert result["controlled_active_limited_allowed"] is False
    assert result["runtime_mode_transition_allowed"] is False
    assert result["runtime_mode_transition_performed"] is False
    assert result["controlled_active_enabled"] is False
    assert result["limited_scheduler_allowed_preview"] is True
    assert result["internal_execution_allowed_preview"] is True
    assert result["state_transition_allowed_preview"] is True
    assert result["real_file_mutation_allowed"] is False
    assert result["runtime_mutation_allowed"] is False
    assert result["external_tool_execution_allowed"] is False
    assert result["network_io_allowed"] is False
    assert result["unbounded_autonomy_allowed"] is False
    assert result["self_start_allowed"] is False
    assert result["blockers"] == []


def test_controlled_active_limited_candidate_blocks_bad_gate_and_modes():
    candidate = build_controlled_active_limited_mode_candidate(
        _payload(
            source_mode="running",
            candidate_mode="full_active",
            gate_review_result={
                "controlled_activation_gate_ready_preview": False,
                "controlled_activation_allowed": True,
            },
        )
    )
    result = evaluate_controlled_active_limited_mode_candidate(candidate)

    assert result["controlled_active_limited_candidate_ready_preview"] is False
    assert "unsupported_source_mode" in result["blockers"]
    assert "unsupported_candidate_mode" in result["blockers"]
    assert "controlled_activation_gate_not_ready" in result["blockers"]
    assert "gate_review_attempted_real_activation" in result["blockers"]


def test_controlled_active_limited_candidate_blocks_scheduler_and_execution_escape():
    candidate = build_controlled_active_limited_mode_candidate(
        _payload(
            limited_scheduler={
                "enabled_preview": False,
                "unbounded_loop": True,
            },
            internal_execution_boundary={
                "internal_execution_allowed_preview": False,
                "external_execution_allowed": True,
            },
            state_transition_boundary={
                "state_transition_allowed_preview": False,
                "real_runtime_state_mutation": True,
            },
        )
    )
    result = evaluate_controlled_active_limited_mode_candidate(candidate)

    assert result["controlled_active_limited_candidate_ready_preview"] is False
    assert "limited_scheduler_not_enabled_preview" in result["blockers"]
    assert "limited_scheduler_unbounded_loop" in result["blockers"]
    assert "internal_execution_not_allowed_preview" in result["blockers"]
    assert "external_execution_not_locked" in result["blockers"]
    assert "state_transition_not_allowed_preview" in result["blockers"]
    assert "real_runtime_state_mutation_not_locked" in result["blockers"]


def test_controlled_active_limited_candidate_blocks_mutation_tool_and_autonomy_unlocks():
    candidate = build_controlled_active_limited_mode_candidate(
        _payload(
            mutation_boundary={
                "real_file_mutation_allowed": True,
                "runtime_mutation_allowed": True,
            },
            tool_boundary={
                "external_tool_execution_allowed": True,
                "network_io_allowed": True,
            },
            autonomy_boundary={
                "unbounded_autonomy_allowed": True,
                "self_start_allowed": True,
            },
            audit_required=False,
        )
    )
    result = evaluate_controlled_active_limited_mode_candidate(candidate)

    assert result["controlled_active_limited_candidate_ready_preview"] is False
    assert "real_file_mutation_not_locked" in result["blockers"]
    assert "runtime_mutation_not_locked" in result["blockers"]
    assert "external_tool_execution_not_locked" in result["blockers"]
    assert "network_io_not_locked" in result["blockers"]
    assert "unbounded_autonomy_not_locked" in result["blockers"]
    assert "self_start_not_locked" in result["blockers"]
    assert "audit_not_required" in result["blockers"]


def test_prepare_controlled_active_limited_candidate_is_disabled_bundle():
    result = prepare_controlled_active_limited_mode_candidate(_payload())

    assert result["enabled"] is False
    assert result["candidate_only"] is True
    assert result["preview_only"] is True
    assert result["controlled_active_limited_allowed"] is False
    assert result["runtime_mode_transition_performed"] is False
    assert result["controlled_active_enabled"] is False
    assert result["limited_scheduler_enabled"] is False
    assert result["internal_execution_enabled"] is False
    assert result["state_transition_enabled"] is False
    assert result["real_file_mutation_performed"] is False
    assert result["runtime_mutation_performed"] is False
    assert result["external_tool_invoked"] is False
    assert result["network_io_performed"] is False
    assert result["unbounded_autonomy_started"] is False
    assert result["self_start_performed"] is False

    assert result["policy_result"]["controlled_active_limited_candidate_ready_preview"] is True
    assert (
        result["projection"]["projected_candidate_status"]
        == "controlled_active_limited_candidate_reserved"
    )
    assert result["audit_record"]["decision"] == "reserved_no_controlled_active_limited_enablement"


def test_controlled_active_limited_candidate_preserves_no_effect_boundary():
    result = prepare_controlled_active_limited_mode_candidate(_payload())

    forbidden_flags = [
        result["controlled_active_limited_allowed"],
        result["runtime_mode_transition_performed"],
        result["controlled_active_enabled"],
        result["limited_scheduler_enabled"],
        result["internal_execution_enabled"],
        result["state_transition_enabled"],
        result["real_file_mutation_performed"],
        result["runtime_mutation_performed"],
        result["external_tool_invoked"],
        result["network_io_performed"],
        result["unbounded_autonomy_started"],
        result["self_start_performed"],
        result["policy_result"]["controlled_active_limited_allowed"],
        result["policy_result"]["runtime_mode_transition_allowed"],
        result["policy_result"]["runtime_mode_transition_performed"],
        result["policy_result"]["controlled_active_enabled"],
        result["policy_result"]["real_file_mutation_allowed"],
        result["policy_result"]["runtime_mutation_allowed"],
        result["policy_result"]["external_tool_execution_allowed"],
        result["policy_result"]["network_io_allowed"],
        result["policy_result"]["unbounded_autonomy_allowed"],
        result["policy_result"]["self_start_allowed"],
        result["projection"]["controlled_active_limited_allowed"],
        result["projection"]["runtime_mode_transition_performed"],
        result["projection"]["controlled_active_enabled"],
        result["projection"]["limited_scheduler_enabled"],
        result["projection"]["internal_execution_enabled"],
        result["projection"]["state_transition_enabled"],
        result["projection"]["real_file_mutation_performed"],
        result["projection"]["runtime_mutation_performed"],
        result["projection"]["external_tool_invoked"],
        result["projection"]["network_io_performed"],
        result["projection"]["unbounded_autonomy_started"],
        result["projection"]["self_start_performed"],
        result["audit_record"]["controlled_active_limited_allowed"],
        result["audit_record"]["runtime_mode_transition_performed"],
        result["audit_record"]["controlled_active_enabled"],
        result["audit_record"]["limited_scheduler_enabled"],
        result["audit_record"]["internal_execution_enabled"],
        result["audit_record"]["state_transition_enabled"],
        result["audit_record"]["real_file_mutation_performed"],
        result["audit_record"]["runtime_mutation_performed"],
        result["audit_record"]["external_tool_invoked"],
        result["audit_record"]["network_io_performed"],
        result["audit_record"]["unbounded_autonomy_started"],
        result["audit_record"]["self_start_performed"],
    ]

    assert forbidden_flags == [False] * len(forbidden_flags)

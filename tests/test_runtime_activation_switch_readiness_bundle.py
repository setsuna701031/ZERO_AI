from __future__ import annotations

import pytest

from core.runtime.runtime_activation_switch_readiness_contract import (
    ACTIVATION_SWITCH_REQUIRED_GATES,
    build_activation_switch_readiness_request,
)
from core.runtime.runtime_activation_switch_readiness_policy import (
    evaluate_activation_switch_readiness,
)
from core.runtime.runtime_activation_switch_readiness import (
    prepare_runtime_activation_switch_readiness,
)


def _gate_results(value=True):
    return {gate_name: value for gate_name in ACTIVATION_SWITCH_REQUIRED_GATES}


def _payload(**overrides):
    payload = {
        "request_id": "activation-switch-1113",
        "operator_id": "operator-1113",
        "target_mode": "controlled_active_candidate",
        "gate_results": _gate_results(True),
        "emergency_disable_available": True,
        "rollback_available": True,
        "operator_control_available": True,
        "audit_required": True,
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def test_activation_switch_readiness_request_requires_identity_gates_and_controls():
    request = build_activation_switch_readiness_request(_payload())

    assert request.request_id == "activation-switch-1113"
    assert request.operator_id == "operator-1113"
    assert request.target_mode == "controlled_active_candidate"
    assert set(request.gate_results) == set(ACTIVATION_SWITCH_REQUIRED_GATES)
    assert request.emergency_disable_available is True
    assert request.rollback_available is True
    assert request.operator_control_available is True
    assert request.audit_required is True


@pytest.mark.parametrize(
    "missing_field",
    [
        "request_id",
        "operator_id",
        "target_mode",
    ],
)
def test_activation_switch_readiness_request_rejects_missing_string_fields(missing_field):
    payload = _payload()
    payload[missing_field] = ""

    with pytest.raises(ValueError):
        build_activation_switch_readiness_request(payload)


@pytest.mark.parametrize(
    "missing_field",
    [
        "gate_results",
        "emergency_disable_available",
        "rollback_available",
        "operator_control_available",
        "audit_required",
    ],
)
def test_activation_switch_readiness_request_rejects_missing_control_fields(missing_field):
    payload = _payload()
    payload.pop(missing_field)

    with pytest.raises(ValueError):
        build_activation_switch_readiness_request(payload)


def test_activation_switch_readiness_request_rejects_non_mapping_gates():
    with pytest.raises(ValueError):
        build_activation_switch_readiness_request(
            _payload(gate_results="not-a-mapping")
        )


def test_activation_switch_policy_can_be_ready_in_preview_but_never_switches():
    request = build_activation_switch_readiness_request(_payload())
    result = evaluate_activation_switch_readiness(request)

    assert result["enabled"] is False
    assert result["readiness_only"] is True
    assert result["preview_only"] is True
    assert result["activation_switch_ready_preview"] is True
    assert result["activation_switch_allowed"] is False
    assert result["runtime_mode_transition_allowed"] is False
    assert result["controlled_active_allowed"] is False
    assert result["real_mutation_allowed"] is False
    assert result["real_tool_execution_allowed"] is False
    assert result["autonomous_execution_allowed"] is False
    assert result["new_task_dispatch_allowed"] is False
    assert result["external_io_allowed"] is False
    assert result["blockers"] == []


def test_activation_switch_policy_reports_missing_gate():
    gates = _gate_results(True)
    gates.pop("queue_finalization")
    request = build_activation_switch_readiness_request(_payload(gate_results=gates))
    result = evaluate_activation_switch_readiness(request)

    assert result["activation_switch_ready_preview"] is False
    assert "queue_finalization" in result["missing_gates"]
    assert "missing_gate:queue_finalization" in result["blockers"]
    assert result["activation_switch_allowed"] is False


def test_activation_switch_policy_reports_failed_gate():
    gates = _gate_results(True)
    gates["real_tool_execution_admission"] = False
    request = build_activation_switch_readiness_request(_payload(gate_results=gates))
    result = evaluate_activation_switch_readiness(request)

    assert result["activation_switch_ready_preview"] is False
    assert "real_tool_execution_admission" in result["failed_gates"]
    assert "gate_not_ready:real_tool_execution_admission" in result["blockers"]
    assert result["activation_switch_allowed"] is False


def test_activation_switch_policy_reports_missing_safety_controls():
    request = build_activation_switch_readiness_request(
        _payload(
            emergency_disable_available=False,
            rollback_available=False,
            operator_control_available=False,
            audit_required=False,
        )
    )
    result = evaluate_activation_switch_readiness(request)

    assert result["activation_switch_ready_preview"] is False
    assert "emergency_disable_missing" in result["blockers"]
    assert "rollback_missing" in result["blockers"]
    assert "operator_control_missing" in result["blockers"]
    assert "audit_not_required" in result["blockers"]


def test_prepare_activation_switch_readiness_is_disabled_bundle():
    result = prepare_runtime_activation_switch_readiness(_payload())

    assert result["enabled"] is False
    assert result["readiness_only"] is True
    assert result["preview_only"] is True
    assert result["activation_switch_allowed"] is False
    assert result["runtime_mode_transition_performed"] is False
    assert result["controlled_active_enabled"] is False
    assert result["real_mutation_enabled"] is False
    assert result["real_tool_execution_enabled"] is False
    assert result["autonomous_execution_enabled"] is False
    assert result["new_task_dispatched"] is False
    assert result["external_io_performed"] is False

    assert result["policy_result"]["activation_switch_ready_preview"] is True
    assert (
        result["projection"]["projected_switch_status"]
        == "activation_switch_readiness_reserved"
    )
    assert result["audit_record"]["decision"] == "reserved_no_activation_switch"


def test_activation_switch_readiness_preserves_no_effect_boundary():
    result = prepare_runtime_activation_switch_readiness(_payload())

    forbidden_flags = [
        result["policy_result"]["activation_switch_allowed"],
        result["policy_result"]["runtime_mode_transition_allowed"],
        result["policy_result"]["controlled_active_allowed"],
        result["policy_result"]["real_mutation_allowed"],
        result["policy_result"]["real_tool_execution_allowed"],
        result["policy_result"]["autonomous_execution_allowed"],
        result["policy_result"]["new_task_dispatch_allowed"],
        result["policy_result"]["external_io_allowed"],
        result["projection"]["runtime_mode_transition_performed"],
        result["projection"]["controlled_active_enabled"],
        result["projection"]["real_mutation_enabled"],
        result["projection"]["real_tool_execution_enabled"],
        result["projection"]["autonomous_execution_enabled"],
        result["projection"]["new_task_dispatched"],
        result["projection"]["external_io_performed"],
        result["audit_record"]["runtime_mode_transition_performed"],
        result["audit_record"]["controlled_active_enabled"],
        result["audit_record"]["real_mutation_enabled"],
        result["audit_record"]["real_tool_execution_enabled"],
        result["audit_record"]["autonomous_execution_enabled"],
        result["audit_record"]["new_task_dispatched"],
        result["audit_record"]["external_io_performed"],
    ]

    assert forbidden_flags == [False] * len(forbidden_flags)

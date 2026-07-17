from __future__ import annotations

import pytest

from core.runtime.runtime_controlled_activation_dry_run import (
    prepare_controlled_activation_dry_run,
)
from core.runtime.runtime_controlled_activation_transaction import (
    build_controlled_activation_dry_run_transaction,
)
from core.runtime.runtime_controlled_activation_transition_simulator import (
    simulate_controlled_activation_transition,
)


def _payload(**overrides):
    payload = {
        "activation_attempt_id": "activation-attempt-1121",
        "transition_id": "transition-1121",
        "request_id": "request-1121",
        "operator_id": "operator-1121",
        "previous_mode": "disabled",
        "target_mode": "controlled_active_candidate",
        "readiness_result": {
            "activation_switch_ready_preview": True,
            "activation_switch_allowed": False,
        },
        "rollback_plan": {
            "available": True,
            "rollback_mode": "disabled",
        },
        "emergency_disable_plan": {
            "available": True,
            "operator_accessible": True,
        },
        "audit_required": True,
        "metadata": {"source": "test"},
    }
    payload.update(overrides)
    return payload


def test_controlled_activation_transaction_requires_identity_modes_and_plans():
    transaction = build_controlled_activation_dry_run_transaction(_payload())

    assert transaction.activation_attempt_id == "activation-attempt-1121"
    assert transaction.transition_id == "transition-1121"
    assert transaction.request_id == "request-1121"
    assert transaction.operator_id == "operator-1121"
    assert transaction.previous_mode == "disabled"
    assert transaction.target_mode == "controlled_active_candidate"
    assert transaction.audit_required is True


@pytest.mark.parametrize(
    "missing_field",
    [
        "activation_attempt_id",
        "transition_id",
        "request_id",
        "operator_id",
        "previous_mode",
        "target_mode",
    ],
)
def test_controlled_activation_transaction_rejects_missing_string_fields(missing_field):
    payload = _payload()
    payload[missing_field] = ""

    with pytest.raises(ValueError):
        build_controlled_activation_dry_run_transaction(payload)


@pytest.mark.parametrize(
    "missing_field",
    [
        "readiness_result",
        "rollback_plan",
        "emergency_disable_plan",
        "audit_required",
    ],
)
def test_controlled_activation_transaction_rejects_missing_object_or_control_fields(missing_field):
    payload = _payload()
    payload.pop(missing_field)

    with pytest.raises(ValueError):
        build_controlled_activation_dry_run_transaction(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "readiness_result",
        "rollback_plan",
        "emergency_disable_plan",
    ],
)
def test_controlled_activation_transaction_rejects_non_mapping_plans(field_name):
    payload = _payload()
    payload[field_name] = "not-a-mapping"

    with pytest.raises(ValueError):
        build_controlled_activation_dry_run_transaction(payload)


def test_transition_simulator_projects_candidate_but_never_changes_mode():
    transaction = build_controlled_activation_dry_run_transaction(_payload())
    result = simulate_controlled_activation_transition(transaction)

    assert result["enabled"] is False
    assert result["dry_run_only"] is True
    assert result["preview_only"] is True
    assert result["transition_ready_preview"] is True
    assert result["projected_mode"] == "controlled_active_candidate"
    assert result["runtime_mode_transition_allowed"] is False
    assert result["runtime_mode_transition_performed"] is False
    assert result["controlled_active_enabled"] is False
    assert result["blockers"] == []


def test_transition_simulator_blocks_failed_readiness():
    transaction = build_controlled_activation_dry_run_transaction(
        _payload(
            readiness_result={
                "activation_switch_ready_preview": False,
                "activation_switch_allowed": False,
            }
        )
    )
    result = simulate_controlled_activation_transition(transaction)

    assert result["transition_ready_preview"] is False
    assert result["projected_mode"] == "disabled"
    assert "activation_switch_readiness_not_ready" in result["blockers"]


def test_transition_simulator_blocks_readiness_that_attempted_real_activation():
    transaction = build_controlled_activation_dry_run_transaction(
        _payload(
            readiness_result={
                "activation_switch_ready_preview": True,
                "activation_switch_allowed": True,
            }
        )
    )
    result = simulate_controlled_activation_transition(transaction)

    assert result["transition_ready_preview"] is False
    assert "readiness_result_attempted_real_activation" in result["blockers"]


def test_prepare_controlled_activation_dry_run_is_complete_disabled_bundle():
    result = prepare_controlled_activation_dry_run(_payload())

    assert result["enabled"] is False
    assert result["dry_run_only"] is True
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

    assert result["transition_result"]["transition_ready_preview"] is True
    assert result["rollback_result"]["rollback_ready_preview"] is True
    assert result["emergency_result"]["emergency_disable_ready_preview"] is True
    assert result["projection"]["dry_run_ready_preview"] is True
    assert result["audit_record"]["decision"] == "reserved_no_controlled_activation"


def test_controlled_activation_dry_run_reports_rollback_blockers():
    result = prepare_controlled_activation_dry_run(
        _payload(rollback_plan={"available": False, "rollback_mode": "wrong"})
    )

    assert result["projection"]["dry_run_ready_preview"] is False
    assert "rollback:rollback_unavailable" in result["projection"]["blockers"]
    assert "rollback:rollback_mode_mismatch" in result["projection"]["blockers"]
    assert result["controlled_activation_allowed"] is False


def test_controlled_activation_dry_run_reports_emergency_disable_blockers():
    result = prepare_controlled_activation_dry_run(
        _payload(emergency_disable_plan={"available": False, "operator_accessible": False})
    )

    assert result["projection"]["dry_run_ready_preview"] is False
    assert "emergency:emergency_disable_unavailable" in result["projection"]["blockers"]
    assert "emergency:emergency_disable_not_operator_accessible" in result["projection"]["blockers"]
    assert result["controlled_activation_allowed"] is False


def test_controlled_activation_dry_run_preserves_no_effect_boundary():
    result = prepare_controlled_activation_dry_run(_payload())

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

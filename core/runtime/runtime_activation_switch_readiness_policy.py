from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_activation_switch_readiness_contract import (
    ACTIVATION_SWITCH_ALLOWED_TARGET_MODES,
    ACTIVATION_SWITCH_FORBIDDEN_EFFECTS,
    ACTIVATION_SWITCH_READINESS_CONTRACT_VERSION,
    ACTIVATION_SWITCH_REQUIRED_GATES,
    RuntimeActivationSwitchReadinessRequest,
)

ACTIVATION_SWITCH_READINESS_POLICY_VERSION = (
    "runtime.activation_switch_readiness.policy.v1.review"
)


def _gate_ready(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("ready") is True:
            return True
        if value.get("status") in {"ready", "passed", "go"}:
            return True
        if value.get("enabled") is False and value.get("preview_only") is True:
            return bool(value.get("admission_ready_preview") or value.get("ready_preview"))
    return value is True


def evaluate_activation_switch_readiness(
    request: RuntimeActivationSwitchReadinessRequest | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(request, RuntimeActivationSwitchReadinessRequest):
        payload = request.to_dict()
    else:
        payload = dict(request)

    target_mode = str(payload.get("target_mode") or "").strip()
    gate_results = payload.get("gate_results") or {}
    emergency_disable_available = bool(payload.get("emergency_disable_available"))
    rollback_available = bool(payload.get("rollback_available"))
    operator_control_available = bool(payload.get("operator_control_available"))
    audit_required = bool(payload.get("audit_required"))

    blockers: list[str] = []
    if target_mode not in ACTIVATION_SWITCH_ALLOWED_TARGET_MODES:
        blockers.append("unsupported_target_mode")
    if not isinstance(gate_results, Mapping):
        blockers.append("gate_results_not_mapping")
        missing_gates = list(ACTIVATION_SWITCH_REQUIRED_GATES)
        failed_gates: list[str] = []
    else:
        missing_gates = [
            gate_name
            for gate_name in ACTIVATION_SWITCH_REQUIRED_GATES
            if gate_name not in gate_results
        ]
        failed_gates = [
            gate_name
            for gate_name in ACTIVATION_SWITCH_REQUIRED_GATES
            if gate_name in gate_results and not _gate_ready(gate_results[gate_name])
        ]
        for gate_name in missing_gates:
            blockers.append(f"missing_gate:{gate_name}")
        for gate_name in failed_gates:
            blockers.append(f"gate_not_ready:{gate_name}")

    if not emergency_disable_available:
        blockers.append("emergency_disable_missing")
    if not rollback_available:
        blockers.append("rollback_missing")
    if not operator_control_available:
        blockers.append("operator_control_missing")
    if not audit_required:
        blockers.append("audit_not_required")

    readiness_preview = not blockers

    return {
        "contract_version": ACTIVATION_SWITCH_READINESS_CONTRACT_VERSION,
        "policy_version": ACTIVATION_SWITCH_READINESS_POLICY_VERSION,
        "enabled": False,
        "readiness_only": True,
        "preview_only": True,
        "activation_switch_ready_preview": readiness_preview,
        "activation_switch_allowed": False,
        "runtime_mode_transition_allowed": False,
        "controlled_active_allowed": False,
        "real_mutation_allowed": False,
        "real_tool_execution_allowed": False,
        "autonomous_execution_allowed": False,
        "new_task_dispatch_allowed": False,
        "external_io_allowed": False,
        "missing_gates": missing_gates,
        "failed_gates": failed_gates,
        "blockers": blockers,
        "forbidden_effects": list(ACTIVATION_SWITCH_FORBIDDEN_EFFECTS),
        "reason": "activation_switch_reserved_for_future_controlled_activation",
    }

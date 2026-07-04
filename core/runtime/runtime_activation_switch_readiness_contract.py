from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

ACTIVATION_SWITCH_READINESS_CONTRACT_VERSION = (
    "runtime.activation_switch_readiness.v1.review"
)

ACTIVATION_SWITCH_REQUIRED_FIELDS = (
    "request_id",
    "operator_id",
    "target_mode",
    "gate_results",
    "emergency_disable_available",
    "rollback_available",
    "operator_control_available",
    "audit_required",
)

ACTIVATION_SWITCH_REQUIRED_GATES = (
    "intent_intake",
    "queue_lifecycle",
    "scheduler_handoff",
    "executor_admission",
    "executor_execution_chain",
    "result_commit_persistence",
    "runtime_state_update_boundary",
    "task_lifecycle_transition_boundary",
    "queue_finalization",
    "runtime_real_mutation_admission",
    "real_tool_execution_admission",
    "autonomous_execution_admission",
)

ACTIVATION_SWITCH_ALLOWED_TARGET_MODES = frozenset(
    {
        "controlled_active_preview",
        "controlled_active_candidate",
    }
)

ACTIVATION_SWITCH_FORBIDDEN_EFFECTS = (
    "set_runtime_mode",
    "enable_real_mutation",
    "enable_real_tool_execution",
    "enable_autonomous_execution",
    "dispatch_new_task",
    "perform_external_io",
)


@dataclass(frozen=True)
class RuntimeActivationSwitchReadinessRequest:
    request_id: str
    operator_id: str
    target_mode: str
    gate_results: Mapping[str, Any]
    emergency_disable_available: bool
    rollback_available: bool
    operator_control_available: bool
    audit_required: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": ACTIVATION_SWITCH_READINESS_CONTRACT_VERSION,
            "request_id": self.request_id,
            "operator_id": self.operator_id,
            "target_mode": self.target_mode,
            "gate_results": dict(self.gate_results),
            "emergency_disable_available": self.emergency_disable_available,
            "rollback_available": self.rollback_available,
            "operator_control_available": self.operator_control_available,
            "audit_required": self.audit_required,
            "metadata": dict(self.metadata),
        }


def build_activation_switch_readiness_request(
    payload: Mapping[str, Any],
) -> RuntimeActivationSwitchReadinessRequest:
    missing = [
        field_name
        for field_name in ("request_id", "operator_id", "target_mode")
        if not str(payload.get(field_name) or "").strip()
    ]
    for required_field in (
        "gate_results",
        "emergency_disable_available",
        "rollback_available",
        "operator_control_available",
        "audit_required",
    ):
        if required_field not in payload:
            missing.append(required_field)
    if missing:
        raise ValueError(
            "missing activation switch readiness fields: " + ", ".join(missing)
        )

    gate_results = payload.get("gate_results")
    if not isinstance(gate_results, Mapping):
        raise ValueError("gate_results must be a mapping")

    return RuntimeActivationSwitchReadinessRequest(
        request_id=str(payload["request_id"]),
        operator_id=str(payload["operator_id"]),
        target_mode=str(payload["target_mode"]),
        gate_results=dict(gate_results),
        emergency_disable_available=bool(payload["emergency_disable_available"]),
        rollback_available=bool(payload["rollback_available"]),
        operator_control_available=bool(payload["operator_control_available"]),
        audit_required=bool(payload["audit_required"]),
        metadata=dict(payload.get("metadata") or {}),
    )

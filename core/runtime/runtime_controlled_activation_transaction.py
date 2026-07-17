from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION = (
    "runtime.controlled_activation_dry_run.v1"
)

CONTROLLED_ACTIVATION_DRY_RUN_REQUIRED_FIELDS = (
    "activation_attempt_id",
    "transition_id",
    "request_id",
    "operator_id",
    "previous_mode",
    "target_mode",
    "readiness_result",
    "rollback_plan",
    "emergency_disable_plan",
    "audit_required",
)

CONTROLLED_ACTIVATION_DRY_RUN_ALLOWED_PREVIOUS_MODES = frozenset(
    {
        "disabled",
        "preview_only",
    }
)

CONTROLLED_ACTIVATION_DRY_RUN_ALLOWED_TARGET_MODES = frozenset(
    {
        "controlled_active_candidate",
        "controlled_active_preview",
    }
)

CONTROLLED_ACTIVATION_DRY_RUN_FORBIDDEN_EFFECTS = (
    "set_runtime_mode",
    "enable_real_mutation",
    "enable_real_tool_execution",
    "enable_autonomous_execution",
    "dispatch_new_task",
    "invoke_tool",
    "perform_external_io",
)


@dataclass(frozen=True)
class ControlledActivationDryRunTransaction:
    activation_attempt_id: str
    transition_id: str
    request_id: str
    operator_id: str
    previous_mode: str
    target_mode: str
    readiness_result: Mapping[str, Any]
    rollback_plan: Mapping[str, Any]
    emergency_disable_plan: Mapping[str, Any]
    audit_required: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
            "activation_attempt_id": self.activation_attempt_id,
            "transition_id": self.transition_id,
            "request_id": self.request_id,
            "operator_id": self.operator_id,
            "previous_mode": self.previous_mode,
            "target_mode": self.target_mode,
            "readiness_result": dict(self.readiness_result),
            "rollback_plan": dict(self.rollback_plan),
            "emergency_disable_plan": dict(self.emergency_disable_plan),
            "audit_required": self.audit_required,
            "metadata": dict(self.metadata),
        }


def build_controlled_activation_dry_run_transaction(
    payload: Mapping[str, Any],
) -> ControlledActivationDryRunTransaction:
    missing = [
        field_name
        for field_name in (
            "activation_attempt_id",
            "transition_id",
            "request_id",
            "operator_id",
            "previous_mode",
            "target_mode",
        )
        if not str(payload.get(field_name) or "").strip()
    ]
    for required_field in (
        "readiness_result",
        "rollback_plan",
        "emergency_disable_plan",
        "audit_required",
    ):
        if required_field not in payload:
            missing.append(required_field)
    if missing:
        raise ValueError(
            "missing controlled activation dry-run fields: " + ", ".join(missing)
        )

    readiness_result = payload.get("readiness_result")
    rollback_plan = payload.get("rollback_plan")
    emergency_disable_plan = payload.get("emergency_disable_plan")

    if not isinstance(readiness_result, Mapping):
        raise ValueError("readiness_result must be a mapping")
    if not isinstance(rollback_plan, Mapping):
        raise ValueError("rollback_plan must be a mapping")
    if not isinstance(emergency_disable_plan, Mapping):
        raise ValueError("emergency_disable_plan must be a mapping")

    return ControlledActivationDryRunTransaction(
        activation_attempt_id=str(payload["activation_attempt_id"]),
        transition_id=str(payload["transition_id"]),
        request_id=str(payload["request_id"]),
        operator_id=str(payload["operator_id"]),
        previous_mode=str(payload["previous_mode"]),
        target_mode=str(payload["target_mode"]),
        readiness_result=dict(readiness_result),
        rollback_plan=dict(rollback_plan),
        emergency_disable_plan=dict(emergency_disable_plan),
        audit_required=bool(payload["audit_required"]),
        metadata=dict(payload.get("metadata") or {}),
    )

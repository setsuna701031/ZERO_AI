from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

CONTROLLED_ACTIVATION_GATE_CONTRACT_VERSION = (
    "runtime.controlled_activation_gate.v1.review"
)

CONTROLLED_ACTIVATION_GATE_REQUIRED_FIELDS = (
    "gate_request_id",
    "activation_attempt_id",
    "transition_id",
    "operator_id",
    "dry_run_result",
    "mode_authority",
    "activation_token",
    "activation_lease",
    "controlled_active_boundary",
    "rollback_authority",
    "kill_switch_authority",
    "audit_required",
)

CONTROLLED_ACTIVATION_GATE_ALLOWED_TARGET_MODES = frozenset(
    {
        "controlled_active_candidate",
        "controlled_active_limited",
    }
)

CONTROLLED_ACTIVATION_GATE_FORBIDDEN_EFFECTS = (
    "set_runtime_mode",
    "enable_real_mutation",
    "enable_real_tool_execution",
    "enable_autonomous_execution",
    "dispatch_new_task",
    "invoke_tool",
    "perform_external_io",
)


@dataclass(frozen=True)
class ControlledActivationGateReviewRequest:
    gate_request_id: str
    activation_attempt_id: str
    transition_id: str
    operator_id: str
    dry_run_result: Mapping[str, Any]
    mode_authority: Mapping[str, Any]
    activation_token: Mapping[str, Any]
    activation_lease: Mapping[str, Any]
    controlled_active_boundary: Mapping[str, Any]
    rollback_authority: Mapping[str, Any]
    kill_switch_authority: Mapping[str, Any]
    audit_required: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTROLLED_ACTIVATION_GATE_CONTRACT_VERSION,
            "gate_request_id": self.gate_request_id,
            "activation_attempt_id": self.activation_attempt_id,
            "transition_id": self.transition_id,
            "operator_id": self.operator_id,
            "dry_run_result": dict(self.dry_run_result),
            "mode_authority": dict(self.mode_authority),
            "activation_token": dict(self.activation_token),
            "activation_lease": dict(self.activation_lease),
            "controlled_active_boundary": dict(self.controlled_active_boundary),
            "rollback_authority": dict(self.rollback_authority),
            "kill_switch_authority": dict(self.kill_switch_authority),
            "audit_required": self.audit_required,
            "metadata": dict(self.metadata),
        }


def build_controlled_activation_gate_review_request(
    payload: Mapping[str, Any],
) -> ControlledActivationGateReviewRequest:
    missing = [
        field_name
        for field_name in (
            "gate_request_id",
            "activation_attempt_id",
            "transition_id",
            "operator_id",
        )
        if not str(payload.get(field_name) or "").strip()
    ]
    for required_field in (
        "dry_run_result",
        "mode_authority",
        "activation_token",
        "activation_lease",
        "controlled_active_boundary",
        "rollback_authority",
        "kill_switch_authority",
        "audit_required",
    ):
        if required_field not in payload:
            missing.append(required_field)
    if missing:
        raise ValueError(
            "missing controlled activation gate fields: " + ", ".join(missing)
        )

    mapping_fields = (
        "dry_run_result",
        "mode_authority",
        "activation_token",
        "activation_lease",
        "controlled_active_boundary",
        "rollback_authority",
        "kill_switch_authority",
    )
    for field_name in mapping_fields:
        if not isinstance(payload.get(field_name), Mapping):
            raise ValueError(f"{field_name} must be a mapping")

    return ControlledActivationGateReviewRequest(
        gate_request_id=str(payload["gate_request_id"]),
        activation_attempt_id=str(payload["activation_attempt_id"]),
        transition_id=str(payload["transition_id"]),
        operator_id=str(payload["operator_id"]),
        dry_run_result=dict(payload["dry_run_result"]),
        mode_authority=dict(payload["mode_authority"]),
        activation_token=dict(payload["activation_token"]),
        activation_lease=dict(payload["activation_lease"]),
        controlled_active_boundary=dict(payload["controlled_active_boundary"]),
        rollback_authority=dict(payload["rollback_authority"]),
        kill_switch_authority=dict(payload["kill_switch_authority"]),
        audit_required=bool(payload["audit_required"]),
        metadata=dict(payload.get("metadata") or {}),
    )

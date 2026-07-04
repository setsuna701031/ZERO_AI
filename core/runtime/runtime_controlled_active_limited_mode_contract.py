from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

CONTROLLED_ACTIVE_LIMITED_MODE_CONTRACT_VERSION = (
    "runtime.controlled_active_limited_mode.v1.candidate"
)

CONTROLLED_ACTIVE_LIMITED_REQUIRED_FIELDS = (
    "candidate_id",
    "activation_attempt_id",
    "operator_id",
    "source_mode",
    "candidate_mode",
    "gate_review_result",
    "limited_scheduler",
    "internal_execution_boundary",
    "state_transition_boundary",
    "mutation_boundary",
    "tool_boundary",
    "autonomy_boundary",
    "audit_required",
)

CONTROLLED_ACTIVE_LIMITED_ALLOWED_SOURCE_MODES = frozenset(
    {
        "disabled",
        "preview_only",
    }
)

CONTROLLED_ACTIVE_LIMITED_ALLOWED_CANDIDATE_MODES = frozenset(
    {
        "controlled_active_limited",
    }
)

CONTROLLED_ACTIVE_LIMITED_FORBIDDEN_EFFECTS = (
    "set_runtime_mode",
    "perform_real_file_mutation",
    "invoke_external_tool",
    "perform_network_io",
    "start_unbounded_autonomy",
    "dispatch_unbounded_task",
)


@dataclass(frozen=True)
class ControlledActiveLimitedModeCandidate:
    candidate_id: str
    activation_attempt_id: str
    operator_id: str
    source_mode: str
    candidate_mode: str
    gate_review_result: Mapping[str, Any]
    limited_scheduler: Mapping[str, Any]
    internal_execution_boundary: Mapping[str, Any]
    state_transition_boundary: Mapping[str, Any]
    mutation_boundary: Mapping[str, Any]
    tool_boundary: Mapping[str, Any]
    autonomy_boundary: Mapping[str, Any]
    audit_required: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTROLLED_ACTIVE_LIMITED_MODE_CONTRACT_VERSION,
            "candidate_id": self.candidate_id,
            "activation_attempt_id": self.activation_attempt_id,
            "operator_id": self.operator_id,
            "source_mode": self.source_mode,
            "candidate_mode": self.candidate_mode,
            "gate_review_result": dict(self.gate_review_result),
            "limited_scheduler": dict(self.limited_scheduler),
            "internal_execution_boundary": dict(self.internal_execution_boundary),
            "state_transition_boundary": dict(self.state_transition_boundary),
            "mutation_boundary": dict(self.mutation_boundary),
            "tool_boundary": dict(self.tool_boundary),
            "autonomy_boundary": dict(self.autonomy_boundary),
            "audit_required": self.audit_required,
            "metadata": dict(self.metadata),
        }


def build_controlled_active_limited_mode_candidate(
    payload: Mapping[str, Any],
) -> ControlledActiveLimitedModeCandidate:
    missing = [
        field_name
        for field_name in (
            "candidate_id",
            "activation_attempt_id",
            "operator_id",
            "source_mode",
            "candidate_mode",
        )
        if not str(payload.get(field_name) or "").strip()
    ]
    for required_field in (
        "gate_review_result",
        "limited_scheduler",
        "internal_execution_boundary",
        "state_transition_boundary",
        "mutation_boundary",
        "tool_boundary",
        "autonomy_boundary",
        "audit_required",
    ):
        if required_field not in payload:
            missing.append(required_field)
    if missing:
        raise ValueError(
            "missing controlled active limited candidate fields: " + ", ".join(missing)
        )

    mapping_fields = (
        "gate_review_result",
        "limited_scheduler",
        "internal_execution_boundary",
        "state_transition_boundary",
        "mutation_boundary",
        "tool_boundary",
        "autonomy_boundary",
    )
    for field_name in mapping_fields:
        if not isinstance(payload.get(field_name), Mapping):
            raise ValueError(f"{field_name} must be a mapping")

    return ControlledActiveLimitedModeCandidate(
        candidate_id=str(payload["candidate_id"]),
        activation_attempt_id=str(payload["activation_attempt_id"]),
        operator_id=str(payload["operator_id"]),
        source_mode=str(payload["source_mode"]),
        candidate_mode=str(payload["candidate_mode"]),
        gate_review_result=dict(payload["gate_review_result"]),
        limited_scheduler=dict(payload["limited_scheduler"]),
        internal_execution_boundary=dict(payload["internal_execution_boundary"]),
        state_transition_boundary=dict(payload["state_transition_boundary"]),
        mutation_boundary=dict(payload["mutation_boundary"]),
        tool_boundary=dict(payload["tool_boundary"]),
        autonomy_boundary=dict(payload["autonomy_boundary"]),
        audit_required=bool(payload["audit_required"]),
        metadata=dict(payload.get("metadata") or {}),
    )

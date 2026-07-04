from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

REAL_TOOL_EXECUTION_ADMISSION_CONTRACT_VERSION = (
    "runtime.real_tool_execution_admission.v1.review"
)

REAL_TOOL_EXECUTION_REQUIRED_FIELDS = (
    "request_id",
    "task_id",
    "tool_name",
    "capability_scope",
    "side_effect_class",
    "executor_authority",
    "audit_required",
)

REAL_TOOL_EXECUTION_ALLOWED_CAPABILITY_SCOPES = frozenset(
    {
        "read_only_runtime_inspection",
        "workspace_read",
        "workspace_write_preview",
        "runtime_mutation_admitted",
    }
)

REAL_TOOL_EXECUTION_ALLOWED_SIDE_EFFECT_CLASSES = frozenset(
    {
        "none",
        "workspace_preview",
        "runtime_admitted",
    }
)

REAL_TOOL_EXECUTION_ACCEPTED_AUTHORITIES = frozenset(
    {
        "executor_admission_gate",
        "runtime_activation_gate",
        "operator_explicit_approval",
        "sealed_test_authority",
    }
)

REAL_TOOL_EXECUTION_FORBIDDEN_EFFECTS = (
    "invoke_tool",
    "perform_tool_side_effect",
    "perform_runtime_mutation",
    "perform_queue_mutation",
    "perform_external_io",
    "autonomous_execution",
)


@dataclass(frozen=True)
class RealToolExecutionAdmissionRequest:
    request_id: str
    task_id: str
    tool_name: str
    capability_scope: str
    side_effect_class: str
    executor_authority: str
    audit_required: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": REAL_TOOL_EXECUTION_ADMISSION_CONTRACT_VERSION,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "capability_scope": self.capability_scope,
            "side_effect_class": self.side_effect_class,
            "executor_authority": self.executor_authority,
            "audit_required": self.audit_required,
            "metadata": dict(self.metadata),
        }


def build_real_tool_execution_admission_request(
    payload: Mapping[str, Any],
) -> RealToolExecutionAdmissionRequest:
    missing = [
        field_name
        for field_name in REAL_TOOL_EXECUTION_REQUIRED_FIELDS
        if field_name != "audit_required" and not str(payload.get(field_name) or "").strip()
    ]
    if "audit_required" not in payload:
        missing.append("audit_required")
    if missing:
        raise ValueError(
            "missing real tool execution admission fields: " + ", ".join(missing)
        )

    return RealToolExecutionAdmissionRequest(
        request_id=str(payload["request_id"]),
        task_id=str(payload["task_id"]),
        tool_name=str(payload["tool_name"]),
        capability_scope=str(payload["capability_scope"]),
        side_effect_class=str(payload["side_effect_class"]),
        executor_authority=str(payload["executor_authority"]),
        audit_required=bool(payload["audit_required"]),
        metadata=dict(payload.get("metadata") or {}),
    )

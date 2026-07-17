from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

REAL_MUTATION_ADMISSION_CONTRACT_VERSION = "runtime.real_mutation_admission.v1.review"

REAL_MUTATION_REQUIRED_FIELDS = (
    "request_id",
    "task_id",
    "mutation_type",
    "target_scope",
    "authority_source",
    "audit_required",
)

REAL_MUTATION_ALLOWED_TYPES = frozenset(
    {
        "runtime_state_update",
        "queue_state_update",
        "task_lifecycle_update",
        "result_persistence_update",
    }
)

REAL_MUTATION_ALLOWED_SCOPES = frozenset(
    {
        "runtime_state",
        "queue",
        "task_lifecycle",
        "result_store",
    }
)

REAL_MUTATION_FORBIDDEN_EFFECTS = (
    "perform_runtime_mutation",
    "perform_queue_mutation",
    "perform_task_lifecycle_mutation",
    "perform_result_store_mutation",
    "tool_execution",
    "autonomous_execution",
    "external_io",
)


@dataclass(frozen=True)
class RuntimeRealMutationAdmissionRequest:
    request_id: str
    task_id: str
    mutation_type: str
    target_scope: str
    authority_source: str
    audit_required: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": REAL_MUTATION_ADMISSION_CONTRACT_VERSION,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "mutation_type": self.mutation_type,
            "target_scope": self.target_scope,
            "authority_source": self.authority_source,
            "audit_required": self.audit_required,
            "metadata": dict(self.metadata),
        }


def build_real_mutation_admission_request(
    payload: Mapping[str, Any],
) -> RuntimeRealMutationAdmissionRequest:
    missing = [
        field_name
        for field_name in REAL_MUTATION_REQUIRED_FIELDS
        if field_name != "audit_required" and not str(payload.get(field_name) or "").strip()
    ]
    if "audit_required" not in payload:
        missing.append("audit_required")
    if missing:
        raise ValueError(f"missing real mutation admission fields: {', '.join(missing)}")

    return RuntimeRealMutationAdmissionRequest(
        request_id=str(payload["request_id"]),
        task_id=str(payload["task_id"]),
        mutation_type=str(payload["mutation_type"]),
        target_scope=str(payload["target_scope"]),
        authority_source=str(payload["authority_source"]),
        audit_required=bool(payload["audit_required"]),
        metadata=dict(payload.get("metadata") or {}),
    )

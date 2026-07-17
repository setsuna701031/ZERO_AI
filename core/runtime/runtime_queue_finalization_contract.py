from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

QUEUE_FINALIZATION_CONTRACT_VERSION = "runtime.queue_finalization.v1.preview"

QUEUE_FINALIZATION_REQUIRED_INPUT_FIELDS = (
    "task_id",
    "queue_item_id",
    "lifecycle_status",
    "result_commit_status",
    "runtime_state_update_status",
)

QUEUE_FINALIZATION_FORBIDDEN_EFFECTS = (
    "queue_mutation",
    "runtime_state_mutation",
    "tool_execution",
    "autonomous_execution",
    "external_io",
)


@dataclass(frozen=True)
class RuntimeQueueFinalizationRequest:
    task_id: str
    queue_item_id: str
    lifecycle_status: str
    result_commit_status: str
    runtime_state_update_status: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": QUEUE_FINALIZATION_CONTRACT_VERSION,
            "task_id": self.task_id,
            "queue_item_id": self.queue_item_id,
            "lifecycle_status": self.lifecycle_status,
            "result_commit_status": self.result_commit_status,
            "runtime_state_update_status": self.runtime_state_update_status,
            "metadata": dict(self.metadata),
        }


def build_queue_finalization_request(payload: Mapping[str, Any]) -> RuntimeQueueFinalizationRequest:
    missing = [
        field_name
        for field_name in QUEUE_FINALIZATION_REQUIRED_INPUT_FIELDS
        if not str(payload.get(field_name) or "").strip()
    ]
    if missing:
        raise ValueError(f"missing queue finalization fields: {', '.join(missing)}")

    return RuntimeQueueFinalizationRequest(
        task_id=str(payload["task_id"]),
        queue_item_id=str(payload["queue_item_id"]),
        lifecycle_status=str(payload["lifecycle_status"]),
        result_commit_status=str(payload["result_commit_status"]),
        runtime_state_update_status=str(payload["runtime_state_update_status"]),
        metadata=dict(payload.get("metadata") or {}),
    )

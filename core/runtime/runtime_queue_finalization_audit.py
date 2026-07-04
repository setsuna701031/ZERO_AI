from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_queue_finalization_contract import QUEUE_FINALIZATION_CONTRACT_VERSION
from core.runtime.runtime_queue_finalization_policy import QUEUE_FINALIZATION_POLICY_VERSION


def build_queue_finalization_audit_record(
    request_payload: Mapping[str, Any],
    policy_result: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": QUEUE_FINALIZATION_CONTRACT_VERSION,
        "policy_version": QUEUE_FINALIZATION_POLICY_VERSION,
        "audit_schema": "runtime.queue_finalization.audit.v1.preview",
        "enabled": False,
        "preview_only": True,
        "task_id": str(request_payload.get("task_id") or ""),
        "queue_item_id": str(request_payload.get("queue_item_id") or ""),
        "decision": "reserved_no_mutation",
        "queue_finalization_allowed": False,
        "queue_mutation_performed": False,
        "runtime_state_mutation_performed": False,
        "tool_execution_performed": False,
        "autonomous_execution_performed": False,
        "finalizable_preview": bool(policy_result.get("finalizable_preview")),
        "blockers": list(policy_result.get("blockers") or []),
        "projection_status": str(projection.get("projected_queue_status") or ""),
    }

from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_queue_finalization_contract import QUEUE_FINALIZATION_CONTRACT_VERSION
from core.runtime.runtime_queue_finalization_policy import QUEUE_FINALIZATION_POLICY_VERSION


def project_queue_finalization_preview(
    request_payload: Mapping[str, Any],
    policy_result: Mapping[str, Any],
) -> dict[str, Any]:
    task_id = str(request_payload.get("task_id") or "")
    queue_item_id = str(request_payload.get("queue_item_id") or "")

    return {
        "contract_version": QUEUE_FINALIZATION_CONTRACT_VERSION,
        "policy_version": QUEUE_FINALIZATION_POLICY_VERSION,
        "enabled": False,
        "preview_only": True,
        "task_id": task_id,
        "queue_item_id": queue_item_id,
        "projected_queue_status": "finalization_preview_reserved",
        "projected_runtime_status": str(request_payload.get("lifecycle_status") or ""),
        "queue_finalization_allowed": False,
        "queue_mutation_performed": False,
        "runtime_state_mutation_performed": False,
        "tool_execution_performed": False,
        "autonomous_execution_performed": False,
        "finalizable_preview": bool(policy_result.get("finalizable_preview")),
        "blockers": list(policy_result.get("blockers") or []),
    }

from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_queue_finalization_contract import build_queue_finalization_request
from core.runtime.runtime_queue_finalization_policy import evaluate_queue_finalization_policy
from core.runtime.runtime_queue_finalization_projection import project_queue_finalization_preview
from core.runtime.runtime_queue_finalization_audit import build_queue_finalization_audit_record


def prepare_runtime_queue_finalization_preview(payload: Mapping[str, Any]) -> dict[str, Any]:
    request = build_queue_finalization_request(payload)
    request_payload = request.to_dict()
    policy_result = evaluate_queue_finalization_policy(request)
    projection = project_queue_finalization_preview(request_payload, policy_result)
    audit_record = build_queue_finalization_audit_record(
        request_payload=request_payload,
        policy_result=policy_result,
        projection=projection,
    )

    return {
        "enabled": False,
        "preview_only": True,
        "request": request_payload,
        "policy_result": policy_result,
        "projection": projection,
        "audit_record": audit_record,
        "queue_finalization_allowed": False,
        "queue_mutation_performed": False,
        "runtime_state_mutation_performed": False,
        "tool_execution_performed": False,
        "autonomous_execution_performed": False,
    }


__all__ = ["prepare_runtime_queue_finalization_preview"]

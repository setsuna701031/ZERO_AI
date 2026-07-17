from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_real_mutation_admission_contract import REAL_MUTATION_ADMISSION_CONTRACT_VERSION
from core.runtime.runtime_real_mutation_admission_policy import REAL_MUTATION_ADMISSION_POLICY_VERSION


def project_real_mutation_admission_review(
    request_payload: Mapping[str, Any],
    policy_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": REAL_MUTATION_ADMISSION_CONTRACT_VERSION,
        "policy_version": REAL_MUTATION_ADMISSION_POLICY_VERSION,
        "enabled": False,
        "review_only": True,
        "preview_only": True,
        "request_id": str(request_payload.get("request_id") or ""),
        "task_id": str(request_payload.get("task_id") or ""),
        "mutation_type": str(request_payload.get("mutation_type") or ""),
        "target_scope": str(request_payload.get("target_scope") or ""),
        "projected_admission_status": "real_mutation_admission_review_reserved",
        "real_mutation_admission_ready_preview": bool(
            policy_result.get("real_mutation_admission_ready_preview")
        ),
        "real_mutation_allowed": False,
        "runtime_state_mutation_performed": False,
        "queue_mutation_performed": False,
        "task_lifecycle_mutation_performed": False,
        "result_store_mutation_performed": False,
        "tool_execution_performed": False,
        "autonomous_execution_performed": False,
        "blockers": list(policy_result.get("blockers") or []),
    }

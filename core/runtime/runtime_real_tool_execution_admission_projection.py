from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_real_tool_execution_admission_contract import (
    REAL_TOOL_EXECUTION_ADMISSION_CONTRACT_VERSION,
)
from core.runtime.runtime_real_tool_execution_admission_policy import (
    REAL_TOOL_EXECUTION_ADMISSION_POLICY_VERSION,
)


def project_real_tool_execution_admission_review(
    request_payload: Mapping[str, Any],
    policy_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": REAL_TOOL_EXECUTION_ADMISSION_CONTRACT_VERSION,
        "policy_version": REAL_TOOL_EXECUTION_ADMISSION_POLICY_VERSION,
        "enabled": False,
        "review_only": True,
        "preview_only": True,
        "request_id": str(request_payload.get("request_id") or ""),
        "task_id": str(request_payload.get("task_id") or ""),
        "tool_name": str(request_payload.get("tool_name") or ""),
        "projected_admission_status": "real_tool_execution_admission_review_reserved",
        "real_tool_execution_admission_ready_preview": bool(
            policy_result.get("real_tool_execution_admission_ready_preview")
        ),
        "real_tool_execution_allowed": False,
        "tool_invocation_performed": False,
        "tool_side_effect_performed": False,
        "runtime_mutation_performed": False,
        "queue_mutation_performed": False,
        "external_io_performed": False,
        "autonomous_execution_performed": False,
        "blockers": list(policy_result.get("blockers") or []),
    }

from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_autonomous_execution_admission_contract import (
    AUTONOMOUS_EXECUTION_ADMISSION_CONTRACT_VERSION,
)
from core.runtime.runtime_autonomous_execution_admission_policy import (
    AUTONOMOUS_EXECUTION_ADMISSION_POLICY_VERSION,
)


def project_autonomous_execution_admission_review(
    request_payload: Mapping[str, Any],
    policy_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": AUTONOMOUS_EXECUTION_ADMISSION_CONTRACT_VERSION,
        "policy_version": AUTONOMOUS_EXECUTION_ADMISSION_POLICY_VERSION,
        "enabled": False,
        "review_only": True,
        "preview_only": True,
        "request_id": str(request_payload.get("request_id") or ""),
        "task_id": str(request_payload.get("task_id") or ""),
        "projected_admission_status": "autonomous_execution_admission_review_reserved",
        "autonomous_execution_admission_ready_preview": bool(
            policy_result.get("autonomous_execution_admission_ready_preview")
        ),
        "autonomous_execution_allowed": False,
        "autonomous_loop_started": False,
        "new_task_dispatched": False,
        "tool_execution_performed": False,
        "runtime_mutation_performed": False,
        "queue_mutation_performed": False,
        "external_io_performed": False,
        "blockers": list(policy_result.get("blockers") or []),
    }

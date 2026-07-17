from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_autonomous_execution_admission_contract import (
    AUTONOMOUS_EXECUTION_ADMISSION_CONTRACT_VERSION,
)
from core.runtime.runtime_autonomous_execution_admission_policy import (
    AUTONOMOUS_EXECUTION_ADMISSION_POLICY_VERSION,
)


def build_autonomous_execution_admission_audit_record(
    request_payload: Mapping[str, Any],
    policy_result: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": AUTONOMOUS_EXECUTION_ADMISSION_CONTRACT_VERSION,
        "policy_version": AUTONOMOUS_EXECUTION_ADMISSION_POLICY_VERSION,
        "audit_schema": "runtime.autonomous_execution_admission.audit.v1.review",
        "enabled": False,
        "review_only": True,
        "preview_only": True,
        "request_id": str(request_payload.get("request_id") or ""),
        "task_id": str(request_payload.get("task_id") or ""),
        "decision": "reserved_no_autonomous_execution",
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
        "projection_status": str(projection.get("projected_admission_status") or ""),
    }

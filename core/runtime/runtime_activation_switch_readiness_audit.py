from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_activation_switch_readiness_contract import (
    ACTIVATION_SWITCH_READINESS_CONTRACT_VERSION,
)
from core.runtime.runtime_activation_switch_readiness_policy import (
    ACTIVATION_SWITCH_READINESS_POLICY_VERSION,
)


def build_activation_switch_readiness_audit_record(
    request_payload: Mapping[str, Any],
    policy_result: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": ACTIVATION_SWITCH_READINESS_CONTRACT_VERSION,
        "policy_version": ACTIVATION_SWITCH_READINESS_POLICY_VERSION,
        "audit_schema": "runtime.activation_switch_readiness.audit.v1.review",
        "enabled": False,
        "readiness_only": True,
        "preview_only": True,
        "request_id": str(request_payload.get("request_id") or ""),
        "operator_id": str(request_payload.get("operator_id") or ""),
        "decision": "reserved_no_activation_switch",
        "activation_switch_ready_preview": bool(
            policy_result.get("activation_switch_ready_preview")
        ),
        "activation_switch_allowed": False,
        "runtime_mode_transition_performed": False,
        "controlled_active_enabled": False,
        "real_mutation_enabled": False,
        "real_tool_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "new_task_dispatched": False,
        "external_io_performed": False,
        "missing_gates": list(policy_result.get("missing_gates") or []),
        "failed_gates": list(policy_result.get("failed_gates") or []),
        "blockers": list(policy_result.get("blockers") or []),
        "projection_status": str(projection.get("projected_switch_status") or ""),
    }

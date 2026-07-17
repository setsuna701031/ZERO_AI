from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_active_limited_mode_contract import (
    CONTROLLED_ACTIVE_LIMITED_MODE_CONTRACT_VERSION,
)
from core.runtime.runtime_controlled_active_limited_mode_policy import (
    CONTROLLED_ACTIVE_LIMITED_MODE_POLICY_VERSION,
)


def build_controlled_active_limited_mode_audit_record(
    candidate_payload: Mapping[str, Any],
    policy_result: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": CONTROLLED_ACTIVE_LIMITED_MODE_CONTRACT_VERSION,
        "policy_version": CONTROLLED_ACTIVE_LIMITED_MODE_POLICY_VERSION,
        "audit_schema": "runtime.controlled_active_limited_mode.audit.v1.candidate",
        "enabled": False,
        "candidate_only": True,
        "preview_only": True,
        "candidate_id": str(candidate_payload.get("candidate_id") or ""),
        "activation_attempt_id": str(candidate_payload.get("activation_attempt_id") or ""),
        "operator_id": str(candidate_payload.get("operator_id") or ""),
        "decision": "reserved_no_controlled_active_limited_enablement",
        "controlled_active_limited_candidate_ready_preview": bool(
            policy_result.get("controlled_active_limited_candidate_ready_preview")
        ),
        "controlled_active_limited_allowed": False,
        "runtime_mode_transition_performed": False,
        "controlled_active_enabled": False,
        "limited_scheduler_enabled": False,
        "internal_execution_enabled": False,
        "state_transition_enabled": False,
        "real_file_mutation_performed": False,
        "runtime_mutation_performed": False,
        "external_tool_invoked": False,
        "network_io_performed": False,
        "unbounded_autonomy_started": False,
        "self_start_performed": False,
        "blockers": list(policy_result.get("blockers") or []),
        "projection_status": str(projection.get("projected_candidate_status") or ""),
    }

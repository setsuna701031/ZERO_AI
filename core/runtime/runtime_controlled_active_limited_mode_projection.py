from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_active_limited_mode_contract import (
    CONTROLLED_ACTIVE_LIMITED_MODE_CONTRACT_VERSION,
)
from core.runtime.runtime_controlled_active_limited_mode_policy import (
    CONTROLLED_ACTIVE_LIMITED_MODE_POLICY_VERSION,
)


def project_controlled_active_limited_mode_candidate(
    candidate_payload: Mapping[str, Any],
    policy_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": CONTROLLED_ACTIVE_LIMITED_MODE_CONTRACT_VERSION,
        "policy_version": CONTROLLED_ACTIVE_LIMITED_MODE_POLICY_VERSION,
        "enabled": False,
        "candidate_only": True,
        "preview_only": True,
        "candidate_id": str(candidate_payload.get("candidate_id") or ""),
        "activation_attempt_id": str(candidate_payload.get("activation_attempt_id") or ""),
        "operator_id": str(candidate_payload.get("operator_id") or ""),
        "source_mode": str(candidate_payload.get("source_mode") or ""),
        "candidate_mode": str(candidate_payload.get("candidate_mode") or ""),
        "projected_candidate_status": "controlled_active_limited_candidate_reserved",
        "projected_mode": str(candidate_payload.get("candidate_mode") or ""),
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
    }

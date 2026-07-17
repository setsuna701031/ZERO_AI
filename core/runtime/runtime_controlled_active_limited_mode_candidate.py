from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_active_limited_mode_audit import (
    build_controlled_active_limited_mode_audit_record,
)
from core.runtime.runtime_controlled_active_limited_mode_contract import (
    build_controlled_active_limited_mode_candidate,
)
from core.runtime.runtime_controlled_active_limited_mode_policy import (
    evaluate_controlled_active_limited_mode_candidate,
)
from core.runtime.runtime_controlled_active_limited_mode_projection import (
    project_controlled_active_limited_mode_candidate,
)


def prepare_controlled_active_limited_mode_candidate(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = build_controlled_active_limited_mode_candidate(payload)
    candidate_payload = candidate.to_dict()
    policy_result = evaluate_controlled_active_limited_mode_candidate(candidate)
    projection = project_controlled_active_limited_mode_candidate(
        candidate_payload=candidate_payload,
        policy_result=policy_result,
    )
    audit_record = build_controlled_active_limited_mode_audit_record(
        candidate_payload=candidate_payload,
        policy_result=policy_result,
        projection=projection,
    )

    return {
        "enabled": False,
        "candidate_only": True,
        "preview_only": True,
        "candidate": candidate_payload,
        "policy_result": policy_result,
        "projection": projection,
        "audit_record": audit_record,
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
    }


__all__ = ["prepare_controlled_active_limited_mode_candidate"]

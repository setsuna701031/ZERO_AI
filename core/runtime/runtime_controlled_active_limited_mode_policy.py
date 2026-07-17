from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_active_limited_mode_contract import (
    CONTROLLED_ACTIVE_LIMITED_ALLOWED_CANDIDATE_MODES,
    CONTROLLED_ACTIVE_LIMITED_ALLOWED_SOURCE_MODES,
    CONTROLLED_ACTIVE_LIMITED_FORBIDDEN_EFFECTS,
    CONTROLLED_ACTIVE_LIMITED_MODE_CONTRACT_VERSION,
    ControlledActiveLimitedModeCandidate,
)

CONTROLLED_ACTIVE_LIMITED_MODE_POLICY_VERSION = (
    "runtime.controlled_active_limited_mode.policy.v1.candidate"
)


def evaluate_controlled_active_limited_mode_candidate(
    candidate: ControlledActiveLimitedModeCandidate | Mapping[str, Any],
) -> dict[str, Any]:
    payload = candidate.to_dict() if isinstance(candidate, ControlledActiveLimitedModeCandidate) else dict(candidate)

    source_mode = str(payload.get("source_mode") or "").strip()
    candidate_mode = str(payload.get("candidate_mode") or "").strip()
    gate_review_result = payload.get("gate_review_result") or {}
    limited_scheduler = payload.get("limited_scheduler") or {}
    internal_execution_boundary = payload.get("internal_execution_boundary") or {}
    state_transition_boundary = payload.get("state_transition_boundary") or {}
    mutation_boundary = payload.get("mutation_boundary") or {}
    tool_boundary = payload.get("tool_boundary") or {}
    autonomy_boundary = payload.get("autonomy_boundary") or {}
    audit_required = bool(payload.get("audit_required"))

    blockers: list[str] = []

    if source_mode not in CONTROLLED_ACTIVE_LIMITED_ALLOWED_SOURCE_MODES:
        blockers.append("unsupported_source_mode")
    if candidate_mode not in CONTROLLED_ACTIVE_LIMITED_ALLOWED_CANDIDATE_MODES:
        blockers.append("unsupported_candidate_mode")

    if not bool(gate_review_result.get("controlled_activation_gate_ready_preview")):
        blockers.append("controlled_activation_gate_not_ready")
    if gate_review_result.get("controlled_activation_allowed") is True:
        blockers.append("gate_review_attempted_real_activation")

    if not bool(limited_scheduler.get("enabled_preview")):
        blockers.append("limited_scheduler_not_enabled_preview")
    if bool(limited_scheduler.get("unbounded_loop")):
        blockers.append("limited_scheduler_unbounded_loop")

    if not bool(internal_execution_boundary.get("internal_execution_allowed_preview")):
        blockers.append("internal_execution_not_allowed_preview")
    if bool(internal_execution_boundary.get("external_execution_allowed")):
        blockers.append("external_execution_not_locked")

    if not bool(state_transition_boundary.get("state_transition_allowed_preview")):
        blockers.append("state_transition_not_allowed_preview")
    if bool(state_transition_boundary.get("real_runtime_state_mutation")):
        blockers.append("real_runtime_state_mutation_not_locked")

    if mutation_boundary.get("real_file_mutation_allowed") is not False:
        blockers.append("real_file_mutation_not_locked")
    if mutation_boundary.get("runtime_mutation_allowed") is not False:
        blockers.append("runtime_mutation_not_locked")

    if tool_boundary.get("external_tool_execution_allowed") is not False:
        blockers.append("external_tool_execution_not_locked")
    if tool_boundary.get("network_io_allowed") is not False:
        blockers.append("network_io_not_locked")

    if autonomy_boundary.get("unbounded_autonomy_allowed") is not False:
        blockers.append("unbounded_autonomy_not_locked")
    if autonomy_boundary.get("self_start_allowed") is not False:
        blockers.append("self_start_not_locked")

    if not audit_required:
        blockers.append("audit_not_required")

    candidate_ready_preview = not blockers

    return {
        "contract_version": CONTROLLED_ACTIVE_LIMITED_MODE_CONTRACT_VERSION,
        "policy_version": CONTROLLED_ACTIVE_LIMITED_MODE_POLICY_VERSION,
        "enabled": False,
        "candidate_only": True,
        "preview_only": True,
        "controlled_active_limited_candidate_ready_preview": candidate_ready_preview,
        "controlled_active_limited_allowed": False,
        "runtime_mode_transition_allowed": False,
        "runtime_mode_transition_performed": False,
        "controlled_active_enabled": False,
        "limited_scheduler_allowed_preview": bool(
            limited_scheduler.get("enabled_preview")
        ) and not bool(limited_scheduler.get("unbounded_loop")),
        "internal_execution_allowed_preview": bool(
            internal_execution_boundary.get("internal_execution_allowed_preview")
        ) and not bool(internal_execution_boundary.get("external_execution_allowed")),
        "state_transition_allowed_preview": bool(
            state_transition_boundary.get("state_transition_allowed_preview")
        ) and not bool(state_transition_boundary.get("real_runtime_state_mutation")),
        "real_file_mutation_allowed": False,
        "runtime_mutation_allowed": False,
        "external_tool_execution_allowed": False,
        "network_io_allowed": False,
        "unbounded_autonomy_allowed": False,
        "self_start_allowed": False,
        "blockers": blockers,
        "forbidden_effects": list(CONTROLLED_ACTIVE_LIMITED_FORBIDDEN_EFFECTS),
        "reason": "controlled_active_limited_mode_candidate_reserved",
    }

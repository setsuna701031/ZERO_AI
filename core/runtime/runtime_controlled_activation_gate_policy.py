from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_activation_gate_contract import (
    CONTROLLED_ACTIVATION_GATE_ALLOWED_TARGET_MODES,
    CONTROLLED_ACTIVATION_GATE_CONTRACT_VERSION,
    CONTROLLED_ACTIVATION_GATE_FORBIDDEN_EFFECTS,
    ControlledActivationGateReviewRequest,
)

CONTROLLED_ACTIVATION_GATE_POLICY_VERSION = "runtime.controlled_activation_gate.policy.v1.review"


def _positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except Exception:
        return False


def evaluate_controlled_activation_gate(
    request: ControlledActivationGateReviewRequest | Mapping[str, Any],
) -> dict[str, Any]:
    payload = request.to_dict() if isinstance(request, ControlledActivationGateReviewRequest) else dict(request)

    dry_run_result = payload.get("dry_run_result") or {}
    mode_authority = payload.get("mode_authority") or {}
    activation_token = payload.get("activation_token") or {}
    activation_lease = payload.get("activation_lease") or {}
    boundary = payload.get("controlled_active_boundary") or {}
    rollback_authority = payload.get("rollback_authority") or {}
    kill_switch_authority = payload.get("kill_switch_authority") or {}
    audit_required = bool(payload.get("audit_required"))

    blockers: list[str] = []

    if not bool(dry_run_result.get("dry_run_ready_preview")):
        blockers.append("dry_run_not_ready")
    if dry_run_result.get("controlled_activation_allowed") is True:
        blockers.append("dry_run_attempted_real_activation")

    if not bool(mode_authority.get("verified")):
        blockers.append("mode_authority_not_verified")
    if mode_authority.get("target_mode") not in CONTROLLED_ACTIVATION_GATE_ALLOWED_TARGET_MODES:
        blockers.append("unsupported_controlled_target_mode")

    if not bool(activation_token.get("valid")):
        blockers.append("activation_token_invalid")
    if not str(activation_token.get("token_id") or "").strip():
        blockers.append("activation_token_missing_id")

    if not bool(activation_lease.get("bounded")):
        blockers.append("activation_lease_unbounded")
    if not _positive_int(activation_lease.get("ttl_seconds")):
        blockers.append("activation_lease_ttl_missing")

    if boundary.get("real_mutation_enabled") is not False:
        blockers.append("boundary_real_mutation_not_locked")
    if boundary.get("real_tool_execution_enabled") is not False:
        blockers.append("boundary_real_tool_execution_not_locked")
    if boundary.get("autonomous_execution_enabled") is not False:
        blockers.append("boundary_autonomous_execution_not_locked")
    if boundary.get("external_io_enabled") is not False:
        blockers.append("boundary_external_io_not_locked")

    if not bool(rollback_authority.get("verified")):
        blockers.append("rollback_authority_not_verified")
    if not bool(kill_switch_authority.get("verified")):
        blockers.append("kill_switch_authority_not_verified")
    if not audit_required:
        blockers.append("audit_not_required")

    gate_ready_preview = not blockers

    return {
        "contract_version": CONTROLLED_ACTIVATION_GATE_CONTRACT_VERSION,
        "policy_version": CONTROLLED_ACTIVATION_GATE_POLICY_VERSION,
        "enabled": False,
        "gate_review_only": True,
        "preview_only": True,
        "controlled_activation_gate_ready_preview": gate_ready_preview,
        "controlled_activation_allowed": False,
        "runtime_mode_transition_allowed": False,
        "controlled_active_enabled": False,
        "real_mutation_enabled": False,
        "real_tool_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "new_task_dispatch_allowed": False,
        "tool_invocation_allowed": False,
        "external_io_allowed": False,
        "blockers": blockers,
        "forbidden_effects": list(CONTROLLED_ACTIVATION_GATE_FORBIDDEN_EFFECTS),
        "reason": "controlled_activation_gate_reserved_for_future_activation",
    }

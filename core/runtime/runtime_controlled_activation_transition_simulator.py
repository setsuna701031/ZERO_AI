from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_activation_transaction import (
    CONTROLLED_ACTIVATION_DRY_RUN_ALLOWED_PREVIOUS_MODES,
    CONTROLLED_ACTIVATION_DRY_RUN_ALLOWED_TARGET_MODES,
    CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
    ControlledActivationDryRunTransaction,
)

CONTROLLED_ACTIVATION_TRANSITION_SIMULATOR_VERSION = (
    "runtime.controlled_activation.transition_simulator.v1"
)


def simulate_controlled_activation_transition(
    transaction: ControlledActivationDryRunTransaction | Mapping[str, Any],
) -> dict[str, Any]:
    payload = transaction.to_dict() if isinstance(transaction, ControlledActivationDryRunTransaction) else dict(transaction)

    previous_mode = str(payload.get("previous_mode") or "").strip()
    target_mode = str(payload.get("target_mode") or "").strip()
    readiness_result = payload.get("readiness_result") or {}

    blockers: list[str] = []
    if previous_mode not in CONTROLLED_ACTIVATION_DRY_RUN_ALLOWED_PREVIOUS_MODES:
        blockers.append("unsupported_previous_mode")
    if target_mode not in CONTROLLED_ACTIVATION_DRY_RUN_ALLOWED_TARGET_MODES:
        blockers.append("unsupported_target_mode")
    if not isinstance(readiness_result, Mapping):
        blockers.append("readiness_result_not_mapping")
        readiness_ready = False
    else:
        readiness_ready = bool(
            readiness_result.get("activation_switch_ready_preview")
            or readiness_result.get("ready")
            or readiness_result.get("ready_preview")
        )
        if not readiness_ready:
            blockers.append("activation_switch_readiness_not_ready")
        if readiness_result.get("activation_switch_allowed") is True:
            blockers.append("readiness_result_attempted_real_activation")

    transition_ready_preview = not blockers

    return {
        "contract_version": CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
        "simulator_version": CONTROLLED_ACTIVATION_TRANSITION_SIMULATOR_VERSION,
        "enabled": False,
        "dry_run_only": True,
        "preview_only": True,
        "activation_attempt_id": str(payload.get("activation_attempt_id") or ""),
        "transition_id": str(payload.get("transition_id") or ""),
        "previous_mode": previous_mode,
        "target_mode": target_mode,
        "transition_ready_preview": transition_ready_preview,
        "projected_mode": target_mode if transition_ready_preview else previous_mode,
        "runtime_mode_transition_allowed": False,
        "runtime_mode_transition_performed": False,
        "controlled_active_enabled": False,
        "blockers": blockers,
    }

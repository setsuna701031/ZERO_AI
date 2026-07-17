from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_activation_transaction import (
    CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
)

CONTROLLED_ACTIVATION_ROLLBACK_SIMULATOR_VERSION = (
    "runtime.controlled_activation.rollback_simulator.v1"
)


def simulate_controlled_activation_rollback(
    transaction_payload: Mapping[str, Any],
    transition_result: Mapping[str, Any],
) -> dict[str, Any]:
    rollback_plan = transaction_payload.get("rollback_plan") or {}
    previous_mode = str(transaction_payload.get("previous_mode") or "disabled")

    blockers: list[str] = []
    if not isinstance(rollback_plan, Mapping):
        blockers.append("rollback_plan_not_mapping")
        rollback_ready = False
    else:
        rollback_ready = bool(rollback_plan.get("available")) and str(
            rollback_plan.get("rollback_mode") or ""
        ).strip() == previous_mode
        if not rollback_plan.get("available"):
            blockers.append("rollback_unavailable")
        if str(rollback_plan.get("rollback_mode") or "").strip() != previous_mode:
            blockers.append("rollback_mode_mismatch")

    return {
        "contract_version": CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
        "rollback_simulator_version": CONTROLLED_ACTIVATION_ROLLBACK_SIMULATOR_VERSION,
        "enabled": False,
        "dry_run_only": True,
        "preview_only": True,
        "rollback_ready_preview": rollback_ready and not blockers,
        "projected_rollback_mode": previous_mode,
        "rollback_allowed": False,
        "rollback_performed": False,
        "runtime_mode_transition_performed": False,
        "blockers": blockers,
        "transition_blockers": list(transition_result.get("blockers") or []),
    }

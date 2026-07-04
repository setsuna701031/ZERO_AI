from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_activation_transaction import (
    CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
)

CONTROLLED_ACTIVATION_EMERGENCY_DISABLE_SIMULATOR_VERSION = (
    "runtime.controlled_activation.emergency_disable_simulator.v1"
)


def simulate_controlled_activation_emergency_disable(
    transaction_payload: Mapping[str, Any],
) -> dict[str, Any]:
    emergency_disable_plan = transaction_payload.get("emergency_disable_plan") or {}
    previous_mode = str(transaction_payload.get("previous_mode") or "disabled")

    blockers: list[str] = []
    if not isinstance(emergency_disable_plan, Mapping):
        blockers.append("emergency_disable_plan_not_mapping")
        emergency_ready = False
    else:
        emergency_ready = bool(emergency_disable_plan.get("available")) and bool(
            emergency_disable_plan.get("operator_accessible")
        )
        if not emergency_disable_plan.get("available"):
            blockers.append("emergency_disable_unavailable")
        if not emergency_disable_plan.get("operator_accessible"):
            blockers.append("emergency_disable_not_operator_accessible")

    return {
        "contract_version": CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
        "emergency_disable_simulator_version": CONTROLLED_ACTIVATION_EMERGENCY_DISABLE_SIMULATOR_VERSION,
        "enabled": False,
        "dry_run_only": True,
        "preview_only": True,
        "emergency_disable_ready_preview": emergency_ready and not blockers,
        "projected_emergency_mode": previous_mode,
        "emergency_disable_allowed": False,
        "emergency_disable_performed": False,
        "runtime_mode_transition_performed": False,
        "blockers": blockers,
    }

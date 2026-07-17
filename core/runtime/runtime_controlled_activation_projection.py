from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_activation_transaction import (
    CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
)

CONTROLLED_ACTIVATION_PROJECTION_VERSION = (
    "runtime.controlled_activation.projection.v1"
)


def project_controlled_activation_dry_run(
    transaction_payload: Mapping[str, Any],
    transition_result: Mapping[str, Any],
    rollback_result: Mapping[str, Any],
    emergency_result: Mapping[str, Any],
) -> dict[str, Any]:
    blockers = (
        list(transition_result.get("blockers") or [])
        + [f"rollback:{item}" for item in rollback_result.get("blockers") or []]
        + [f"emergency:{item}" for item in emergency_result.get("blockers") or []]
    )

    dry_run_ready_preview = (
        bool(transition_result.get("transition_ready_preview"))
        and bool(rollback_result.get("rollback_ready_preview"))
        and bool(emergency_result.get("emergency_disable_ready_preview"))
        and not blockers
    )

    return {
        "contract_version": CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
        "projection_version": CONTROLLED_ACTIVATION_PROJECTION_VERSION,
        "enabled": False,
        "dry_run_only": True,
        "preview_only": True,
        "activation_attempt_id": str(transaction_payload.get("activation_attempt_id") or ""),
        "transition_id": str(transaction_payload.get("transition_id") or ""),
        "previous_mode": str(transaction_payload.get("previous_mode") or ""),
        "target_mode": str(transaction_payload.get("target_mode") or ""),
        "projected_mode": transition_result.get("projected_mode"),
        "dry_run_ready_preview": dry_run_ready_preview,
        "controlled_activation_allowed": False,
        "runtime_mode_transition_performed": False,
        "controlled_active_enabled": False,
        "real_mutation_enabled": False,
        "real_tool_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "new_task_dispatched": False,
        "tool_invoked": False,
        "external_io_performed": False,
        "blockers": blockers,
    }

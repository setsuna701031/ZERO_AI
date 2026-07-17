from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_activation_transaction import (
    CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
)

CONTROLLED_ACTIVATION_AUDIT_VERSION = "runtime.controlled_activation.audit.v1"


def build_controlled_activation_dry_run_audit_record(
    transaction_payload: Mapping[str, Any],
    transition_result: Mapping[str, Any],
    rollback_result: Mapping[str, Any],
    emergency_result: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "contract_version": CONTROLLED_ACTIVATION_DRY_RUN_CONTRACT_VERSION,
        "audit_schema": CONTROLLED_ACTIVATION_AUDIT_VERSION,
        "enabled": False,
        "dry_run_only": True,
        "preview_only": True,
        "activation_attempt_id": str(transaction_payload.get("activation_attempt_id") or ""),
        "transition_id": str(transaction_payload.get("transition_id") or ""),
        "request_id": str(transaction_payload.get("request_id") or ""),
        "operator_id": str(transaction_payload.get("operator_id") or ""),
        "decision": "reserved_no_controlled_activation",
        "dry_run_ready_preview": bool(projection.get("dry_run_ready_preview")),
        "transition_ready_preview": bool(transition_result.get("transition_ready_preview")),
        "rollback_ready_preview": bool(rollback_result.get("rollback_ready_preview")),
        "emergency_disable_ready_preview": bool(
            emergency_result.get("emergency_disable_ready_preview")
        ),
        "controlled_activation_allowed": False,
        "runtime_mode_transition_performed": False,
        "controlled_active_enabled": False,
        "real_mutation_enabled": False,
        "real_tool_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "new_task_dispatched": False,
        "tool_invoked": False,
        "external_io_performed": False,
        "blockers": list(projection.get("blockers") or []),
        "projection_status": "controlled_activation_dry_run_reserved",
    }

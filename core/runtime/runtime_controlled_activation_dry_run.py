from __future__ import annotations

from typing import Any, Mapping

from core.runtime.runtime_controlled_activation_audit import (
    build_controlled_activation_dry_run_audit_record,
)
from core.runtime.runtime_controlled_activation_emergency_disable import (
    simulate_controlled_activation_emergency_disable,
)
from core.runtime.runtime_controlled_activation_projection import (
    project_controlled_activation_dry_run,
)
from core.runtime.runtime_controlled_activation_rollback import (
    simulate_controlled_activation_rollback,
)
from core.runtime.runtime_controlled_activation_transaction import (
    build_controlled_activation_dry_run_transaction,
)
from core.runtime.runtime_controlled_activation_transition_simulator import (
    simulate_controlled_activation_transition,
)


def prepare_controlled_activation_dry_run(payload: Mapping[str, Any]) -> dict[str, Any]:
    transaction = build_controlled_activation_dry_run_transaction(payload)
    transaction_payload = transaction.to_dict()
    transition_result = simulate_controlled_activation_transition(transaction)
    rollback_result = simulate_controlled_activation_rollback(
        transaction_payload=transaction_payload,
        transition_result=transition_result,
    )
    emergency_result = simulate_controlled_activation_emergency_disable(
        transaction_payload=transaction_payload,
    )
    projection = project_controlled_activation_dry_run(
        transaction_payload=transaction_payload,
        transition_result=transition_result,
        rollback_result=rollback_result,
        emergency_result=emergency_result,
    )
    audit_record = build_controlled_activation_dry_run_audit_record(
        transaction_payload=transaction_payload,
        transition_result=transition_result,
        rollback_result=rollback_result,
        emergency_result=emergency_result,
        projection=projection,
    )

    return {
        "enabled": False,
        "dry_run_only": True,
        "preview_only": True,
        "transaction": transaction_payload,
        "transition_result": transition_result,
        "rollback_result": rollback_result,
        "emergency_result": emergency_result,
        "projection": projection,
        "audit_record": audit_record,
        "controlled_activation_allowed": False,
        "runtime_mode_transition_performed": False,
        "controlled_active_enabled": False,
        "real_mutation_enabled": False,
        "real_tool_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "new_task_dispatched": False,
        "tool_invoked": False,
        "external_io_performed": False,
    }


__all__ = ["prepare_controlled_activation_dry_run"]

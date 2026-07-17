"""Disabled final safety gate for runtime queue mutation activation.

This module prepares final readiness metadata before any future queue mutation
execution. It does not mutate queues, write queue data, call storage, begin or
commit transactions, import scheduler or executor code, run tools, start
workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_mutation_final_gate"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_mutation_final_gate(
    queue_mutation_dry_run_preview: object = None,
) -> dict:
    """Return a deterministic disabled final queue mutation safety preview."""

    is_mapping = isinstance(queue_mutation_dry_run_preview, Mapping)
    source = queue_mutation_dry_run_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    audit_snapshot = _snapshot_mapping(source.get("audit_snapshot"))
    authorization_snapshot = _snapshot_mapping(
        audit_snapshot.get("authorization_snapshot")
    )
    mutation_plan_preview = _snapshot_mapping(source.get("mutation_plan_preview"))
    dry_run_snapshot = {
        "dry_run_status": source.get("dry_run_status"),
        "dry_run_reason": source.get("dry_run_reason"),
        "mutation_plan_created": source.get("mutation_plan_created", False),
        "mutation_execution_allowed": source.get(
            "mutation_execution_allowed", False
        ),
        "audit_snapshot": audit_snapshot,
        "authorization_snapshot": authorization_snapshot,
        "mutation_plan_preview": mutation_plan_preview,
    }
    safety_check_passed = bool(audit_snapshot and authorization_snapshot)

    return {
        "enabled": False,
        "mode": "queue_mutation_final_gate_preview",
        "preview_only": True,
        "input_present": queue_mutation_dry_run_preview is not None,
        "input_type": type(queue_mutation_dry_run_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "final_gate_ready": True,
        "safety_check_passed": safety_check_passed,
        "mutation_execution_authorized": False,
        "queue_mutation_allowed": False,
        "runtime_mutation_allowed": False,
        "final_gate_status": "disabled",
        "final_gate_reason": "queue_mutation_final_gate_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "dry_run_snapshot": dry_run_snapshot,
        "final_mutation_readiness_preview": {
            "readiness_layer": "runtime_queue_mutation_final_gate",
            "authorization_chain_present": bool(authorization_snapshot),
            "audit_chain_present": bool(audit_snapshot),
            "safety_check_passed": safety_check_passed,
            "execution_authorized": False,
        },
        "queue_write_allowed": False,
        "storage_call_allowed": False,
        "transaction_begin_allowed": False,
        "transaction_commit_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_mutation_final_gate_disabled",
    }

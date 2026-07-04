"""Disabled queue mutation dry-run planner for runtime activation.

This module prepares future queue mutation plan metadata after the audit
preview. It does not create executable plans, write queues, execute
transactions, call storage, import scheduler or executor code, run tools, start
workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_mutation_dry_run"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_mutation_dry_run(
    queue_mutation_audit_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue mutation dry-run preview."""

    is_mapping = isinstance(queue_mutation_audit_preview, Mapping)
    source = queue_mutation_audit_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    authorization_snapshot = _snapshot_mapping(source.get("authorization_snapshot"))
    audit_snapshot = {
        "audit_status": source.get("audit_status"),
        "audit_reason": source.get("audit_reason"),
        "audit_record_created": source.get("audit_record_created", False),
        "audit_persistence_allowed": source.get("audit_persistence_allowed", False),
        "mutation_audited": source.get("mutation_audited", False),
        "authorization_snapshot": authorization_snapshot,
    }

    return {
        "enabled": False,
        "mode": "queue_mutation_dry_run_preview",
        "preview_only": True,
        "input_present": queue_mutation_audit_preview is not None,
        "input_type": type(queue_mutation_audit_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "dry_run_ready": True,
        "mutation_plan_created": False,
        "mutation_execution_allowed": False,
        "queue_mutation_allowed": False,
        "runtime_mutation_allowed": False,
        "dry_run_status": "disabled",
        "dry_run_reason": "queue_mutation_dry_run_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "audit_snapshot": audit_snapshot,
        "mutation_plan_preview": {
            "plan_type": "runtime_queue_mutation",
            "plan_created": False,
            "execution_enabled": False,
            "persistence_enabled": False,
            "queue_write_enabled": False,
            "runtime_write_enabled": False,
        },
        "transaction_execution_allowed": False,
        "queue_write_allowed": False,
        "storage_call_allowed": False,
        "persistence_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_mutation_dry_run_disabled",
    }

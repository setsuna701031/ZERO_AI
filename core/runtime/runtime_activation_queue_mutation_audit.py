"""Disabled queue mutation audit preview for runtime activation.

This module prepares audit/evidence metadata before any future queue mutation.
It does not create audit records, persist audit data, write queues, call
storage, import scheduler or executor code, run tools, start workers, or mutate
runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_mutation_audit"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_mutation_audit(
    queue_mutation_authorization_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue mutation audit preview."""

    is_mapping = isinstance(queue_mutation_authorization_preview, Mapping)
    source = queue_mutation_authorization_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    authorization_snapshot = {
        "authority_status": source.get("authority_status"),
        "authority_reason": source.get("authority_reason"),
        "mutation_authorized": source.get("mutation_authorized", False),
        "queue_mutation_allowed": source.get("queue_mutation_allowed", False),
        "runtime_mutation_allowed": source.get("runtime_mutation_allowed", False),
    }

    return {
        "enabled": False,
        "mode": "queue_mutation_audit_preview",
        "preview_only": True,
        "input_present": queue_mutation_authorization_preview is not None,
        "input_type": type(queue_mutation_authorization_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "audit_boundary_ready": True,
        "audit_record_created": False,
        "audit_persistence_allowed": False,
        "mutation_audited": False,
        "queue_mutation_allowed": False,
        "runtime_mutation_allowed": False,
        "audit_status": "disabled",
        "audit_reason": "queue_mutation_audit_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "authorization_snapshot": authorization_snapshot,
        "future_audit_evidence_preview": {
            "evidence_layer": "runtime_queue_mutation",
            "audit_record_available": False,
            "audit_record_created": False,
            "audit_persistence_enabled": False,
            "mutation_audited": False,
        },
        "audit_file_write_allowed": False,
        "database_write_allowed": False,
        "storage_call_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_mutation_audit_disabled",
    }

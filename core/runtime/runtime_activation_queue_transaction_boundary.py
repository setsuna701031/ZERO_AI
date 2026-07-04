"""Disabled queue transaction boundary preview for runtime activation.

This module previews future transaction metadata only. It does not begin,
commit, or roll back transactions; write files; mutate queues; call scheduler
or executor code; run tools; start background workers; or mutate runtime state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_transaction_boundary"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_transaction_boundary(
    queue_storage_adapter_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue transaction boundary preview."""

    is_mapping = isinstance(queue_storage_adapter_preview, Mapping)
    source = queue_storage_adapter_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))

    return {
        "enabled": False,
        "mode": "queue_transaction_boundary_preview",
        "preview_only": True,
        "input_present": queue_storage_adapter_preview is not None,
        "input_type": type(queue_storage_adapter_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "transaction_boundary_ready": True,
        "transaction_available": False,
        "transaction_begin_allowed": False,
        "transaction_commit_allowed": False,
        "transaction_rollback_available": False,
        "queue_mutation_allowed": False,
        "runtime_mutation_allowed": False,
        "transaction_status": "disabled",
        "transaction_reason": "queue_transaction_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "future_transaction_preview": {
            "transaction_type": "persistent_queue_mutation",
            "begin_enabled": False,
            "commit_enabled": False,
            "rollback_available": False,
            "write_enabled": False,
        },
        "filesystem_write_allowed": False,
        "database_write_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_transaction_boundary_disabled",
    }

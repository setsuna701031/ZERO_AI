"""Disabled queue mutation authorization preview for runtime activation.

This module produces the final authorization decision layer before any future
queue mutation. It does not write queues, execute transactions, call storage,
import scheduler or executor code, run tools, start workers, or mutate
runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_mutation_authorization"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_mutation_authorization(
    queue_transaction_boundary_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue mutation authorization preview."""

    is_mapping = isinstance(queue_transaction_boundary_preview, Mapping)
    source = queue_transaction_boundary_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))

    return {
        "enabled": False,
        "mode": "queue_mutation_authorization_preview",
        "preview_only": True,
        "input_present": queue_transaction_boundary_preview is not None,
        "input_type": type(queue_transaction_boundary_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "mutation_authorization_ready": True,
        "mutation_authorized": False,
        "queue_mutation_allowed": False,
        "runtime_mutation_allowed": False,
        "authority_status": "disabled",
        "authority_reason": "queue_mutation_authorization_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "future_mutation_authorization_preview": {
            "authorization_layer": "runtime_queue_mutation",
            "authority_available": False,
            "mutation_authorized": False,
            "queue_write_enabled": False,
            "runtime_write_enabled": False,
        },
        "transaction_execution_allowed": False,
        "queue_write_allowed": False,
        "storage_call_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_mutation_authorization_disabled",
    }

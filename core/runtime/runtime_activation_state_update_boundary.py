"""Disabled runtime state update boundary for runtime activation.

This module prepares future runtime state update metadata after the executor
result persistence boundary. It does not import or call executor code, call
tools, update runtime state, update task state, update queues, spawn
subprocesses, call scheduler runtime code, perform filesystem or database IO,
start workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_state_update"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_state_update(
    executor_result_persistence_preview: object = None,
) -> dict:
    """Return a deterministic disabled runtime state update preview."""

    is_mapping = isinstance(executor_result_persistence_preview, Mapping)
    source = executor_result_persistence_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    result_commit_snapshot = _snapshot_mapping(source.get("result_commit_snapshot"))
    result_persistence_preview = _snapshot_mapping(
        source.get("result_persistence_preview")
    )
    result_persistence_snapshot = {
        "persistence_status": source.get("persistence_status"),
        "persistence_reason": source.get("persistence_reason"),
        "result_persistence_ready": source.get("result_persistence_ready", False),
        "result_persisted": source.get("result_persisted", False),
        "persistence_allowed": source.get("persistence_allowed", False),
        "state_update_allowed": source.get("state_update_allowed", False),
        "queue_update_allowed": source.get("queue_update_allowed", False),
        "state_transition_allowed": source.get("state_transition_allowed", False),
        "execution_allowed": source.get("execution_allowed", False),
        "tool_execution_allowed": source.get("tool_execution_allowed", False),
        "tool_call_allowed": source.get("tool_call_allowed", False),
        "runtime_mutation_allowed": source.get("runtime_mutation_allowed", False),
        "repo_mutation_allowed": source.get("repo_mutation_allowed", False),
        "result_commit_snapshot": result_commit_snapshot,
        "result_persistence_preview": result_persistence_preview,
    }

    return {
        "enabled": False,
        "mode": "runtime_state_update_preview",
        "preview_only": True,
        "input_present": executor_result_persistence_preview is not None,
        "input_type": type(executor_result_persistence_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "state_update_ready": True,
        "state_update_allowed": False,
        "runtime_state_updated": False,
        "task_state_updated": False,
        "queue_state_updated": False,
        "state_persistence_allowed": False,
        "task_lifecycle_transition_allowed": False,
        "queue_finalization_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "state_update_status": "disabled",
        "state_update_reason": "runtime_state_update_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "result_persistence_snapshot": result_persistence_snapshot,
        "state_update_preview": {
            "state_update_layer": "runtime_activation_state_update",
            "runtime_state_updated": False,
            "task_state_updated": False,
            "queue_state_updated": False,
            "state_update_enabled": False,
            "task_lifecycle_transition_enabled": False,
            "queue_finalization_enabled": False,
        },
        "queue_read_allowed": False,
        "queue_write_allowed": False,
        "filesystem_io_allowed": False,
        "database_io_allowed": False,
        "scheduler_runtime_call_allowed": False,
        "executor_call_allowed": False,
        "tool_import_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "runtime_state_update_disabled",
    }

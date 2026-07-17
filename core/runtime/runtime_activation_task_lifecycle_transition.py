"""Disabled task lifecycle transition boundary for runtime activation.

This module prepares future task lifecycle transition metadata after the
runtime state update boundary. It does not import or call scheduler code,
executor code, tools, queue storage, runtime state machines, spawn subprocesses,
perform filesystem or database IO, start workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_task_lifecycle_transition"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_task_lifecycle_transition(
    runtime_state_update_preview: object = None,
) -> dict:
    """Return a deterministic disabled task lifecycle transition preview."""

    is_mapping = isinstance(runtime_state_update_preview, Mapping)
    source = runtime_state_update_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    result_persistence_snapshot = _snapshot_mapping(
        source.get("result_persistence_snapshot")
    )
    state_update_preview = _snapshot_mapping(source.get("state_update_preview"))
    state_update_snapshot = {
        "state_update_status": source.get("state_update_status"),
        "state_update_reason": source.get("state_update_reason"),
        "state_update_ready": source.get("state_update_ready", False),
        "state_update_allowed": source.get("state_update_allowed", False),
        "runtime_state_updated": source.get("runtime_state_updated", False),
        "task_state_updated": source.get("task_state_updated", False),
        "queue_state_updated": source.get("queue_state_updated", False),
        "state_persistence_allowed": source.get("state_persistence_allowed", False),
        "task_lifecycle_transition_allowed": source.get(
            "task_lifecycle_transition_allowed", False
        ),
        "queue_finalization_allowed": source.get("queue_finalization_allowed", False),
        "execution_allowed": source.get("execution_allowed", False),
        "tool_execution_allowed": source.get("tool_execution_allowed", False),
        "tool_call_allowed": source.get("tool_call_allowed", False),
        "runtime_mutation_allowed": source.get("runtime_mutation_allowed", False),
        "repo_mutation_allowed": source.get("repo_mutation_allowed", False),
        "result_persistence_snapshot": result_persistence_snapshot,
        "state_update_preview": state_update_preview,
    }

    return {
        "enabled": False,
        "mode": "runtime_task_lifecycle_transition_preview",
        "preview_only": True,
        "input_present": runtime_state_update_preview is not None,
        "input_type": type(runtime_state_update_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "transition_boundary_ready": True,
        "task_lifecycle_transition_ready": True,
        "task_lifecycle_transition_allowed": False,
        "task_transition_allowed": False,
        "queue_transition_allowed": False,
        "runtime_transition_allowed": False,
        "task_state_changed": False,
        "queue_state_changed": False,
        "runtime_state_changed": False,
        "queue_finalization_allowed": False,
        "state_persistence_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "transition_status": "disabled",
        "transition_reason": "runtime_task_lifecycle_transition_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "state_update_snapshot": state_update_snapshot,
        "task_lifecycle_transition_preview": {
            "transition_layer": "runtime_activation_task_lifecycle_transition",
            "task_state_changed": False,
            "queue_state_changed": False,
            "runtime_state_changed": False,
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
        "reason": "runtime_task_lifecycle_transition_disabled",
    }

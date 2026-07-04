"""Disabled executor execution completion boundary for runtime activation.

This module prepares future executor execution completion metadata after the
executor execution start boundary. It does not import or call executor code,
call tools, commit results, transition state, update queues, spawn subprocesses,
call scheduler runtime code, perform filesystem or database IO, start workers,
or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_executor_execution_completion"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_executor_execution_completion(
    executor_execution_start_preview: object = None,
) -> dict:
    """Return a deterministic disabled executor execution completion preview."""

    is_mapping = isinstance(executor_execution_start_preview, Mapping)
    source = executor_execution_start_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    execution_authorization_snapshot = _snapshot_mapping(
        source.get("execution_authorization_snapshot")
    )
    execution_start_preview = _snapshot_mapping(
        source.get("execution_start_preview")
    )
    execution_start_snapshot = {
        "execution_start_status": source.get("execution_start_status"),
        "execution_start_reason": source.get("execution_start_reason"),
        "execution_start_boundary_ready": source.get(
            "execution_start_boundary_ready", False
        ),
        "executor_runtime_available": source.get(
            "executor_runtime_available", False
        ),
        "execution_start_requested": source.get(
            "execution_start_requested", False
        ),
        "execution_start_allowed": source.get("execution_start_allowed", False),
        "execution_started": source.get("execution_started", False),
        "execution_completed": source.get("execution_completed", False),
        "execution_allowed": source.get("execution_allowed", False),
        "tool_execution_allowed": source.get("tool_execution_allowed", False),
        "tool_call_allowed": source.get("tool_call_allowed", False),
        "runtime_mutation_allowed": source.get(
            "runtime_mutation_allowed", False
        ),
        "repo_mutation_allowed": source.get("repo_mutation_allowed", False),
        "execution_authorization_snapshot": execution_authorization_snapshot,
        "execution_start_preview": execution_start_preview,
    }

    return {
        "enabled": False,
        "mode": "executor_execution_completion_preview",
        "preview_only": True,
        "input_present": executor_execution_start_preview is not None,
        "input_type": type(executor_execution_start_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "execution_completion_ready": True,
        "execution_completed": False,
        "execution_result_created": False,
        "result_commit_allowed": False,
        "queue_update_allowed": False,
        "state_transition_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "completion_status": "disabled",
        "completion_reason": "executor_execution_completion_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "execution_start_snapshot": execution_start_snapshot,
        "execution_completion_preview": {
            "completion_layer": "runtime_executor_execution_completion",
            "execution_completed": False,
            "execution_result_created": False,
            "result_commit_enabled": False,
            "queue_update_enabled": False,
            "state_transition_enabled": False,
            "repo_mutation_enabled": False,
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
        "reason": "executor_execution_completion_disabled",
    }

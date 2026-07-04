"""Disabled executor result commit boundary for runtime activation.

This module prepares future executor result commit metadata after the executor
execution completion boundary. It does not import or call executor code, call
tools, commit results, transition state, update queues, spawn subprocesses,
call scheduler runtime code, perform filesystem or database IO, start workers,
or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_executor_result_commit"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_executor_result_commit(
    executor_execution_completion_preview: object = None,
) -> dict:
    """Return a deterministic disabled executor result commit preview."""

    is_mapping = isinstance(executor_execution_completion_preview, Mapping)
    source = executor_execution_completion_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    execution_start_snapshot = _snapshot_mapping(
        source.get("execution_start_snapshot")
    )
    execution_completion_preview = _snapshot_mapping(
        source.get("execution_completion_preview")
    )
    execution_completion_snapshot = {
        "completion_status": source.get("completion_status"),
        "completion_reason": source.get("completion_reason"),
        "execution_completion_ready": source.get(
            "execution_completion_ready", False
        ),
        "execution_completed": source.get("execution_completed", False),
        "execution_result_created": source.get(
            "execution_result_created", False
        ),
        "result_commit_allowed": source.get("result_commit_allowed", False),
        "queue_update_allowed": source.get("queue_update_allowed", False),
        "state_transition_allowed": source.get(
            "state_transition_allowed", False
        ),
        "execution_allowed": source.get("execution_allowed", False),
        "tool_execution_allowed": source.get("tool_execution_allowed", False),
        "tool_call_allowed": source.get("tool_call_allowed", False),
        "runtime_mutation_allowed": source.get(
            "runtime_mutation_allowed", False
        ),
        "repo_mutation_allowed": source.get("repo_mutation_allowed", False),
        "execution_start_snapshot": execution_start_snapshot,
        "execution_completion_preview": execution_completion_preview,
    }

    return {
        "enabled": False,
        "mode": "executor_result_commit_preview",
        "preview_only": True,
        "input_present": executor_execution_completion_preview is not None,
        "input_type": type(executor_execution_completion_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "result_commit_boundary_ready": True,
        "result_commit_prepared": True,
        "result_commit_executed": False,
        "result_persistence_allowed": False,
        "queue_update_allowed": False,
        "state_transition_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "commit_status": "disabled",
        "commit_reason": "executor_result_commit_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "execution_completion_snapshot": execution_completion_snapshot,
        "result_commit_preview": {
            "commit_layer": "runtime_executor_result_commit",
            "result_commit_executed": False,
            "result_persistence_enabled": False,
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
        "reason": "executor_result_commit_disabled",
    }

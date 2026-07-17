"""Disabled executor result persistence boundary for runtime activation.

This module prepares future executor result persistence metadata after the
executor result commit boundary. It does not import or call executor code,
call tools, persist results, update runtime state, update queues, spawn
subprocesses, call scheduler runtime code, perform filesystem or database IO,
start workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_executor_result_persistence"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_executor_result_persistence(
    executor_result_commit_preview: object = None,
) -> dict:
    """Return a deterministic disabled executor result persistence preview."""

    is_mapping = isinstance(executor_result_commit_preview, Mapping)
    source = executor_result_commit_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    execution_completion_snapshot = _snapshot_mapping(
        source.get("execution_completion_snapshot")
    )
    result_commit_preview = _snapshot_mapping(source.get("result_commit_preview"))
    result_commit_snapshot = {
        "commit_status": source.get("commit_status"),
        "commit_reason": source.get("commit_reason"),
        "result_commit_boundary_ready": source.get(
            "result_commit_boundary_ready", False
        ),
        "result_commit_prepared": source.get("result_commit_prepared", False),
        "result_commit_executed": source.get("result_commit_executed", False),
        "result_persistence_allowed": source.get(
            "result_persistence_allowed", False
        ),
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
        "execution_completion_snapshot": execution_completion_snapshot,
        "result_commit_preview": result_commit_preview,
    }

    return {
        "enabled": False,
        "mode": "executor_result_persistence_preview",
        "preview_only": True,
        "input_present": executor_result_commit_preview is not None,
        "input_type": type(executor_result_commit_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "result_persistence_ready": True,
        "result_persisted": False,
        "persistence_allowed": False,
        "state_update_allowed": False,
        "queue_update_allowed": False,
        "state_transition_allowed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "persistence_status": "disabled",
        "persistence_reason": "executor_result_persistence_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "result_commit_snapshot": result_commit_snapshot,
        "result_persistence_preview": {
            "persistence_layer": "runtime_executor_result_persistence",
            "result_persisted": False,
            "persistence_enabled": False,
            "state_update_enabled": False,
            "queue_update_enabled": False,
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
        "reason": "executor_result_persistence_disabled",
    }

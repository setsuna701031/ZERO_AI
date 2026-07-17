"""Disabled executor tool boundary for runtime activation.

This module prepares future executor tool boundary metadata after executor
runtime boundary. It does not import or call tool code, import or call
executor code, spawn subprocesses, call scheduler runtime code, read or
write queues, perform filesystem or database IO, start workers, or mutate
runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_executor_tool_boundary"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_executor_tool_boundary(
    executor_runtime_boundary_preview: object = None,
) -> dict:
    """Return a deterministic disabled executor tool boundary preview."""

    is_mapping = isinstance(executor_runtime_boundary_preview, Mapping)
    source = executor_runtime_boundary_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    executor_admission_snapshot = _snapshot_mapping(
        source.get("executor_admission_snapshot")
    )
    executor_runtime_preview = _snapshot_mapping(
        source.get("executor_runtime_preview")
    )
    executor_runtime_snapshot = {
        "runtime_status": source.get("runtime_status"),
        "runtime_reason": source.get("runtime_reason"),
        "executor_runtime_boundary_ready": source.get(
            "executor_runtime_boundary_ready", False
        ),
        "executor_runtime_available": source.get(
            "executor_runtime_available", False
        ),
        "execution_started": source.get("execution_started", False),
        "execution_completed": source.get("execution_completed", False),
        "execution_allowed": source.get("execution_allowed", False),
        "tool_execution_allowed": source.get(
            "tool_execution_allowed", False
        ),
        "runtime_mutation_allowed": source.get(
            "runtime_mutation_allowed", False
        ),
        "repo_mutation_allowed": source.get("repo_mutation_allowed", False),
        "executor_admission_snapshot": executor_admission_snapshot,
        "executor_runtime_preview": executor_runtime_preview,
    }

    return {
        "enabled": False,
        "mode": "executor_tool_boundary_preview",
        "preview_only": True,
        "input_present": executor_runtime_boundary_preview is not None,
        "input_type": type(executor_runtime_boundary_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "tool_boundary_ready": True,
        "tool_runtime_available": False,
        "tool_execution_allowed": False,
        "tool_call_started": False,
        "tool_call_completed": False,
        "execution_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "tool_boundary_status": "disabled",
        "tool_boundary_reason": "executor_tool_boundary_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "executor_runtime_snapshot": executor_runtime_snapshot,
        "executor_tool_preview": {
            "tool_layer": "runtime_executor_tool_boundary",
            "tool_runtime_available": False,
            "tool_call_enabled": False,
            "tool_call_started": False,
            "tool_call_completed": False,
            "execution_enabled": False,
        },
        "queue_read_allowed": False,
        "queue_write_allowed": False,
        "filesystem_io_allowed": False,
        "database_io_allowed": False,
        "scheduler_runtime_call_allowed": False,
        "executor_call_allowed": False,
        "tool_import_allowed": False,
        "tool_call_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "executor_tool_boundary_disabled",
    }

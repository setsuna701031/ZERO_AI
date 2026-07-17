"""Disabled executor execution plan boundary for runtime activation.

This module prepares future executor execution plan metadata after executor
tool boundary. It does not import or call tool code, import or call executor
code, spawn subprocesses, call scheduler runtime code, read or write queues,
perform filesystem or database IO, start workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_executor_execution_plan"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_executor_execution_plan(
    executor_tool_boundary_preview: object = None,
) -> dict:
    """Return a deterministic disabled executor execution plan preview."""

    is_mapping = isinstance(executor_tool_boundary_preview, Mapping)
    source = executor_tool_boundary_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    executor_runtime_snapshot = _snapshot_mapping(
        source.get("executor_runtime_snapshot")
    )
    executor_tool_preview = _snapshot_mapping(source.get("executor_tool_preview"))
    executor_tool_snapshot = {
        "tool_boundary_status": source.get("tool_boundary_status"),
        "tool_boundary_reason": source.get("tool_boundary_reason"),
        "tool_boundary_ready": source.get("tool_boundary_ready", False),
        "tool_runtime_available": source.get("tool_runtime_available", False),
        "tool_execution_allowed": source.get("tool_execution_allowed", False),
        "tool_call_started": source.get("tool_call_started", False),
        "tool_call_completed": source.get("tool_call_completed", False),
        "execution_allowed": source.get("execution_allowed", False),
        "runtime_mutation_allowed": source.get(
            "runtime_mutation_allowed", False
        ),
        "repo_mutation_allowed": source.get("repo_mutation_allowed", False),
        "executor_runtime_snapshot": executor_runtime_snapshot,
        "executor_tool_preview": executor_tool_preview,
    }

    return {
        "enabled": False,
        "mode": "executor_execution_plan_preview",
        "preview_only": True,
        "input_present": executor_tool_boundary_preview is not None,
        "input_type": type(executor_tool_boundary_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "execution_plan_ready": True,
        "execution_plan_created": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_plan_status": "disabled",
        "execution_plan_reason": "executor_execution_plan_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "executor_tool_snapshot": executor_tool_snapshot,
        "execution_plan_preview": {
            "plan_layer": "runtime_executor_execution_plan",
            "execution_plan_available": False,
            "execution_plan_created": False,
            "execution_enabled": False,
            "tool_execution_enabled": False,
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
        "reason": "executor_execution_plan_disabled",
    }

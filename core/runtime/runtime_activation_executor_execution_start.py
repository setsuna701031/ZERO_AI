"""Disabled executor execution start boundary for runtime activation.

This module prepares future executor execution start metadata after the
executor execution authorization gate. It does not import or call executor
code, call tools, spawn subprocesses, call scheduler runtime code, read or
write queues, perform filesystem or database IO, start workers, or mutate
runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_executor_execution_start"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_executor_execution_start(
    executor_execution_authorization_preview: object = None,
) -> dict:
    """Return a deterministic disabled executor execution start preview."""

    is_mapping = isinstance(executor_execution_authorization_preview, Mapping)
    source = executor_execution_authorization_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    execution_plan_snapshot = _snapshot_mapping(source.get("execution_plan_snapshot"))
    execution_authorization_preview = _snapshot_mapping(
        source.get("execution_authorization_preview")
    )
    execution_authorization_snapshot = {
        "authorization_status": source.get("authorization_status"),
        "authorization_reason": source.get("authorization_reason"),
        "execution_authorization_ready": source.get(
            "execution_authorization_ready", False
        ),
        "execution_authorized": source.get("execution_authorized", False),
        "executor_start_allowed": source.get("executor_start_allowed", False),
        "execution_allowed": source.get("execution_allowed", False),
        "tool_execution_allowed": source.get("tool_execution_allowed", False),
        "tool_call_allowed": source.get("tool_call_allowed", False),
        "runtime_mutation_allowed": source.get(
            "runtime_mutation_allowed", False
        ),
        "repo_mutation_allowed": source.get("repo_mutation_allowed", False),
        "execution_plan_snapshot": execution_plan_snapshot,
        "execution_authorization_preview": execution_authorization_preview,
    }

    return {
        "enabled": False,
        "mode": "executor_execution_start_preview",
        "preview_only": True,
        "input_present": executor_execution_authorization_preview is not None,
        "input_type": type(executor_execution_authorization_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "execution_start_boundary_ready": True,
        "executor_runtime_available": False,
        "execution_start_requested": False,
        "execution_start_allowed": False,
        "execution_started": False,
        "execution_completed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "tool_call_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "execution_start_status": "disabled",
        "execution_start_reason": "executor_execution_start_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "execution_authorization_snapshot": execution_authorization_snapshot,
        "execution_start_preview": {
            "start_layer": "runtime_executor_execution_start",
            "executor_runtime_available": False,
            "execution_start_enabled": False,
            "execution_started": False,
            "execution_completed": False,
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
        "reason": "executor_execution_start_disabled",
    }

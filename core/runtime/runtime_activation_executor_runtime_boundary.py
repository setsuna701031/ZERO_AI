"""Disabled executor runtime boundary for runtime activation.

This module prepares future executor runtime metadata after executor
admission. It does not import or call executor code, call tools, spawn
subprocesses, call scheduler runtime code, read or write queues, perform
filesystem or database IO, start workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_executor_runtime_boundary"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_executor_runtime_boundary(
    executor_admission_preview: object = None,
) -> dict:
    """Return a deterministic disabled executor runtime boundary preview."""

    is_mapping = isinstance(executor_admission_preview, Mapping)
    source = executor_admission_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    scheduler_dispatch_snapshot = _snapshot_mapping(
        source.get("scheduler_dispatch_snapshot")
    )
    admission_preview = _snapshot_mapping(source.get("executor_admission_preview"))
    executor_admission_snapshot = {
        "admission_status": source.get("admission_status"),
        "admission_reason": source.get("admission_reason"),
        "executor_admission_ready": source.get(
            "executor_admission_ready", False
        ),
        "executor_available": source.get("executor_available", False),
        "executor_admission_granted": source.get(
            "executor_admission_granted", False
        ),
        "execution_allowed": source.get("execution_allowed", False),
        "tool_execution_allowed": source.get(
            "tool_execution_allowed", False
        ),
        "runtime_mutation_allowed": source.get(
            "runtime_mutation_allowed", False
        ),
        "scheduler_dispatch_snapshot": scheduler_dispatch_snapshot,
        "executor_admission_preview": admission_preview,
    }

    return {
        "enabled": False,
        "mode": "executor_runtime_boundary_preview",
        "preview_only": True,
        "input_present": executor_admission_preview is not None,
        "input_type": type(executor_admission_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "executor_runtime_boundary_ready": True,
        "executor_runtime_available": False,
        "execution_started": False,
        "execution_completed": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "runtime_mutation_allowed": False,
        "repo_mutation_allowed": False,
        "runtime_status": "disabled",
        "runtime_reason": "executor_runtime_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "executor_admission_snapshot": executor_admission_snapshot,
        "executor_runtime_preview": {
            "runtime_layer": "runtime_executor_boundary",
            "executor_runtime_available": False,
            "runtime_started": False,
            "runtime_completed": False,
            "execution_enabled": False,
            "tool_execution_enabled": False,
        },
        "queue_read_allowed": False,
        "queue_write_allowed": False,
        "filesystem_io_allowed": False,
        "database_io_allowed": False,
        "scheduler_runtime_call_allowed": False,
        "executor_call_allowed": False,
        "tool_call_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "executor_runtime_disabled",
    }

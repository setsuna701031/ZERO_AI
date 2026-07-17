"""Disabled executor admission boundary for runtime activation.

This module prepares future executor admission metadata after scheduler
dispatch. It does not import or call executor code, call tools, spawn
subprocesses, call scheduler runtime code, read or write queues, perform
filesystem or database IO, start workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_executor_admission"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_executor_admission(
    scheduler_dispatch_preview: object = None,
) -> dict:
    """Return a deterministic disabled executor admission preview."""

    is_mapping = isinstance(scheduler_dispatch_preview, Mapping)
    source = scheduler_dispatch_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    scheduler_planning_snapshot = _snapshot_mapping(
        source.get("scheduler_planning_snapshot")
    )
    dispatch_preview = _snapshot_mapping(source.get("dispatch_preview"))
    scheduler_dispatch_snapshot = {
        "dispatch_status": source.get("dispatch_status"),
        "dispatch_reason": source.get("dispatch_reason"),
        "scheduler_dispatch_ready": source.get(
            "scheduler_dispatch_ready", False
        ),
        "dispatch_created": source.get("dispatch_created", False),
        "dispatch_allowed": source.get("dispatch_allowed", False),
        "execution_allowed": source.get("execution_allowed", False),
        "executor_admission_allowed": source.get(
            "executor_admission_allowed", False
        ),
        "scheduler_planning_snapshot": scheduler_planning_snapshot,
        "dispatch_preview": dispatch_preview,
    }

    return {
        "enabled": False,
        "mode": "executor_admission_preview",
        "preview_only": True,
        "input_present": scheduler_dispatch_preview is not None,
        "input_type": type(scheduler_dispatch_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "executor_admission_ready": True,
        "executor_available": False,
        "executor_admission_granted": False,
        "execution_allowed": False,
        "tool_execution_allowed": False,
        "runtime_mutation_allowed": False,
        "admission_status": "disabled",
        "admission_reason": "executor_admission_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "scheduler_dispatch_snapshot": scheduler_dispatch_snapshot,
        "executor_admission_preview": {
            "admission_layer": "runtime_executor_admission",
            "executor_available": False,
            "admission_granted": False,
            "execution_enabled": False,
            "tool_execution_enabled": False,
        },
        "queue_read_allowed": False,
        "queue_write_allowed": False,
        "filesystem_io_allowed": False,
        "database_io_allowed": False,
        "scheduler_runtime_call_allowed": False,
        "executor_call_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "executor_admission_disabled",
    }

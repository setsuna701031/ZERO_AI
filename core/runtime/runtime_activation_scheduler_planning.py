"""Disabled scheduler planning boundary for runtime activation.

This module prepares future scheduling plan metadata after scheduler intake. It
does not import or call scheduler runtime code, call executor code, read or
write queues, perform filesystem or database IO, run tools, start workers, or
mutate runtime state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_scheduler_planning"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_scheduler_planning(
    scheduler_intake_preview: object = None,
) -> dict:
    """Return a deterministic disabled scheduler planning preview."""

    is_mapping = isinstance(scheduler_intake_preview, Mapping)
    source = scheduler_intake_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    visibility_snapshot = _snapshot_mapping(source.get("visibility_snapshot"))
    scheduler_intake_shape = _snapshot_mapping(
        source.get("future_scheduler_intake_preview")
    )
    scheduler_intake_snapshot = {
        "scheduler_status": source.get("scheduler_status"),
        "scheduler_reason": source.get("scheduler_reason"),
        "scheduler_intake_ready": source.get("scheduler_intake_ready", False),
        "scheduler_available": source.get("scheduler_available", False),
        "scheduler_task_received": source.get(
            "scheduler_task_received", False
        ),
        "scheduling_allowed": source.get("scheduling_allowed", False),
        "execution_allowed": source.get("execution_allowed", False),
        "visibility_snapshot": visibility_snapshot,
        "future_scheduler_intake_preview": scheduler_intake_shape,
    }

    return {
        "enabled": False,
        "mode": "scheduler_planning_preview",
        "preview_only": True,
        "input_present": scheduler_intake_preview is not None,
        "input_type": type(scheduler_intake_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "scheduler_planning_ready": True,
        "scheduling_plan_created": False,
        "scheduling_allowed": False,
        "dispatch_allowed": False,
        "execution_allowed": False,
        "runtime_mutation_allowed": False,
        "planning_status": "disabled",
        "planning_reason": "scheduler_planning_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "scheduler_intake_snapshot": scheduler_intake_snapshot,
        "scheduling_plan_preview": {
            "plan_layer": "runtime_scheduler_planning",
            "plan_created": False,
            "scheduling_enabled": False,
            "dispatch_enabled": False,
            "execution_enabled": False,
        },
        "queue_read_allowed": False,
        "queue_write_allowed": False,
        "filesystem_io_allowed": False,
        "database_io_allowed": False,
        "scheduler_runtime_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "scheduler_planning_disabled",
    }

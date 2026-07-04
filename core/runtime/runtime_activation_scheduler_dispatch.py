"""Disabled scheduler dispatch boundary for runtime activation.

This module prepares future dispatch metadata after scheduler planning. It does
not call scheduler runtime code, import or call executor code, read or write
queues, perform filesystem or database IO, run tools, start workers, or mutate
runtime state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_scheduler_dispatch"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_scheduler_dispatch(
    scheduler_planning_preview: object = None,
) -> dict:
    """Return a deterministic disabled scheduler dispatch preview."""

    is_mapping = isinstance(scheduler_planning_preview, Mapping)
    source = scheduler_planning_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    scheduler_intake_snapshot = _snapshot_mapping(
        source.get("scheduler_intake_snapshot")
    )
    scheduling_plan_preview = _snapshot_mapping(
        source.get("scheduling_plan_preview")
    )
    scheduler_planning_snapshot = {
        "planning_status": source.get("planning_status"),
        "planning_reason": source.get("planning_reason"),
        "scheduler_planning_ready": source.get(
            "scheduler_planning_ready", False
        ),
        "scheduling_plan_created": source.get(
            "scheduling_plan_created", False
        ),
        "scheduling_allowed": source.get("scheduling_allowed", False),
        "dispatch_allowed": source.get("dispatch_allowed", False),
        "execution_allowed": source.get("execution_allowed", False),
        "scheduler_intake_snapshot": scheduler_intake_snapshot,
        "scheduling_plan_preview": scheduling_plan_preview,
    }

    return {
        "enabled": False,
        "mode": "scheduler_dispatch_preview",
        "preview_only": True,
        "input_present": scheduler_planning_preview is not None,
        "input_type": type(scheduler_planning_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "scheduler_dispatch_ready": True,
        "dispatch_created": False,
        "dispatch_allowed": False,
        "execution_allowed": False,
        "executor_admission_allowed": False,
        "runtime_mutation_allowed": False,
        "dispatch_status": "disabled",
        "dispatch_reason": "scheduler_dispatch_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "scheduler_planning_snapshot": scheduler_planning_snapshot,
        "dispatch_preview": {
            "dispatch_layer": "runtime_scheduler_dispatch",
            "dispatch_created": False,
            "dispatch_enabled": False,
            "executor_admission_enabled": False,
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
        "reason": "scheduler_dispatch_disabled",
    }

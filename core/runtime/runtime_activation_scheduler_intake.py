"""Disabled scheduler intake boundary for runtime activation.

This module prepares future scheduler intake metadata after the queue
visibility gate. It does not import or call scheduler code, call executor code,
read or write queues, perform filesystem or database IO, run tools, start
workers, or mutate runtime state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_scheduler_intake"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_scheduler_intake(
    queue_visibility_gate_preview: object = None,
) -> dict:
    """Return a deterministic disabled scheduler intake preview."""

    is_mapping = isinstance(queue_visibility_gate_preview, Mapping)
    source = queue_visibility_gate_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    queue_state_snapshot = _snapshot_mapping(source.get("queue_state_snapshot"))
    scheduler_visibility_preview = _snapshot_mapping(
        source.get("future_scheduler_visibility_preview")
    )
    visibility_snapshot = {
        "visibility_status": source.get("visibility_status"),
        "visibility_reason": source.get("visibility_reason"),
        "visibility_gate_ready": source.get("visibility_gate_ready", False),
        "queue_visible": source.get("queue_visible", False),
        "scheduler_visibility_allowed": source.get(
            "scheduler_visibility_allowed", False
        ),
        "task_discovery_allowed": source.get("task_discovery_allowed", False),
        "queue_state_snapshot": queue_state_snapshot,
        "future_scheduler_visibility_preview": scheduler_visibility_preview,
    }

    return {
        "enabled": False,
        "mode": "scheduler_intake_preview",
        "preview_only": True,
        "input_present": queue_visibility_gate_preview is not None,
        "input_type": type(queue_visibility_gate_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "scheduler_intake_ready": True,
        "scheduler_available": False,
        "scheduler_task_received": False,
        "scheduling_allowed": False,
        "execution_allowed": False,
        "runtime_mutation_allowed": False,
        "scheduler_status": "disabled",
        "scheduler_reason": "scheduler_intake_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "visibility_snapshot": visibility_snapshot,
        "future_scheduler_intake_preview": {
            "intake_layer": "runtime_scheduler_visible_queue_task",
            "scheduler_available": False,
            "task_receive_enabled": False,
            "scheduling_enabled": False,
            "execution_enabled": False,
        },
        "queue_read_allowed": False,
        "queue_write_allowed": False,
        "filesystem_io_allowed": False,
        "database_io_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "scheduler_intake_disabled",
    }

"""Disabled queue writer boundary preview for runtime activation.

This module previews future queue record metadata only. It does not write queue
records, perform file IO, import queue implementations, call scheduler or
executor code, run tools, start background loops, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_writer_boundary"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_writer_boundary(
    queue_persistence_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue writer boundary preview."""

    is_mapping = isinstance(queue_persistence_preview, Mapping)
    source = queue_persistence_preview if is_mapping else {}

    identity_source = source.get("identity_snapshot", source.get("task_identity"))
    lineage_source = source.get("lineage_snapshot", source.get("lineage"))

    identity_snapshot = _snapshot_mapping(identity_source)
    lineage_snapshot = _snapshot_mapping(lineage_source)

    return {
        "enabled": False,
        "mode": "queue_writer_boundary_preview",
        "preview_only": True,
        "input_present": queue_persistence_preview is not None,
        "input_type": type(queue_persistence_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "writer_boundary_ready": True,
        "queue_writer_available": False,
        "queue_record_write_allowed": False,
        "queue_file_write_allowed": False,
        "runtime_mutation_allowed": False,
        "writer_status": "disabled",
        "writer_reason": "queue_writer_disabled",
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "future_queue_record_preview": {
            "record_type": "runtime_queue_task",
            "record_status": "future_package",
            "write_enabled": False,
            "identity_keys": sorted(identity_snapshot.keys()),
            "lineage_keys": sorted(lineage_snapshot.keys()),
        },
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_loop_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_writer_boundary_disabled",
    }

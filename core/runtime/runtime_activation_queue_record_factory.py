"""Disabled queue record factory preview for runtime activation.

This module builds deterministic future queue record preview data only. It does
not insert queues, write files, import queue storage, call scheduler or
executor code, run tools, or mutate runtime state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_record_factory"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_record_factory(
    queue_writer_boundary_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue record factory preview."""

    is_mapping = isinstance(queue_writer_boundary_preview, Mapping)
    source = queue_writer_boundary_preview if is_mapping else {}

    identity_snapshot = _snapshot_mapping(source.get("identity_snapshot"))
    lineage_snapshot = _snapshot_mapping(source.get("lineage_snapshot"))
    writer_record_preview = _snapshot_mapping(source.get("future_queue_record_preview"))

    queue_record_preview = {
        "record_kind": "runtime_queue_task",
        "record_version": 1,
        "record_status": "preview_only",
        "identity": identity_snapshot,
        "lineage": lineage_snapshot,
        "writer_record_preview": writer_record_preview,
        "persist_enabled": False,
        "execution_enabled": False,
    }

    return {
        "enabled": False,
        "mode": "queue_record_factory_preview",
        "preview_only": True,
        "input_present": queue_writer_boundary_preview is not None,
        "input_type": type(queue_writer_boundary_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "record_factory_ready": True,
        "queue_record_created": False,
        "queue_record_persisted": False,
        "queue_record_execution_allowed": False,
        "runtime_mutation_allowed": False,
        "record_status": "disabled",
        "record_reason": "queue_record_factory_disabled",
        "queue_record_preview": queue_record_preview,
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "queue_insert_allowed": False,
        "file_write_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_record_factory_disabled",
    }

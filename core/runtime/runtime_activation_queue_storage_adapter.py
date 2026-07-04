"""Disabled queue storage adapter preview for runtime activation.

This module validates future queue record shape and prepares storage adapter
preview metadata only. It does not write files or databases, import queue
storage implementations, call scheduler or executor code, run tools, start
background loops, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_storage_adapter"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_storage_adapter(
    queue_record_factory_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue storage adapter preview."""

    is_mapping = isinstance(queue_record_factory_preview, Mapping)
    source = queue_record_factory_preview if is_mapping else {}

    record_preview = _snapshot_mapping(source.get("queue_record_preview"))
    identity_source = source.get("identity_snapshot", record_preview.get("identity"))
    lineage_source = source.get("lineage_snapshot", record_preview.get("lineage"))

    identity_snapshot = _snapshot_mapping(identity_source)
    lineage_snapshot = _snapshot_mapping(lineage_source)

    return {
        "enabled": False,
        "mode": "queue_storage_adapter_preview",
        "preview_only": True,
        "input_present": queue_record_factory_preview is not None,
        "input_type": type(queue_record_factory_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "storage_adapter_ready": True,
        "storage_adapter_available": False,
        "storage_write_allowed": False,
        "queue_storage_mutated": False,
        "runtime_mutation_allowed": False,
        "storage_status": "disabled",
        "storage_reason": "queue_storage_adapter_disabled",
        "storage_target_preview": {
            "target_type": "persistent_runtime_queue",
            "target_status": "future_package",
            "adapter_available": False,
            "write_enabled": False,
            "record_shape_valid": bool(record_preview),
        },
        "identity_snapshot": identity_snapshot,
        "lineage_snapshot": lineage_snapshot,
        "queue_record_preview": record_preview,
        "filesystem_write_allowed": False,
        "database_write_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_loop_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_storage_adapter_disabled",
    }

"""Disabled queue persistence preview for runtime activation.

This module produces future persistence target metadata only. It does not
write queues, perform file IO, import queue implementations, call scheduler or
executor code, run tools, start workers, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_persistence"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_persistence(
    queue_commit_gate_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue persistence preview."""

    is_mapping = isinstance(queue_commit_gate_preview, Mapping)
    source = queue_commit_gate_preview if is_mapping else {}

    identity_source = source.get("identity_snapshot", source.get("task_identity"))
    lineage_source = source.get("lineage_snapshot", source.get("lineage"))

    return {
        "enabled": False,
        "mode": "queue_persistence_preview",
        "preview_only": True,
        "input_present": queue_commit_gate_preview is not None,
        "input_type": type(queue_commit_gate_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "persistence_preview_ready": True,
        "queue_persistence_allowed": False,
        "queue_write_allowed": False,
        "runtime_mutation_allowed": False,
        "persistence_status": "disabled",
        "persistence_reason": "queue_persistence_disabled",
        "identity_snapshot": _snapshot_mapping(identity_source),
        "lineage_snapshot": _snapshot_mapping(lineage_source),
        "future_persistence_target": {
            "target_type": "runtime_queue",
            "target_status": "future_package",
            "write_enabled": False,
        },
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_persistence_preview_disabled",
    }

"""Disabled queue commit gate preview for runtime activation.

This module produces commit authorization metadata only. It does not import
queue implementations, write files, call scheduler or executor code, run tools,
start workers, persist data, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_commit_gate"]


def _snapshot_mapping(value: object) -> dict:
    if isinstance(value, Mapping):
        return dict(sorted(value.items()))
    return {}


def preview_runtime_activation_queue_commit_gate(
    queue_admission_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue commit gate preview."""

    is_mapping = isinstance(queue_admission_preview, Mapping)
    source = queue_admission_preview if is_mapping else {}

    return {
        "enabled": False,
        "mode": "queue_commit_gate_preview",
        "preview_only": True,
        "input_present": queue_admission_preview is not None,
        "input_type": type(queue_admission_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "commit_gate_ready": True,
        "queue_commit_allowed": False,
        "mutation_allowed": False,
        "persistence_allowed": False,
        "commit_reason": "queue_commit_disabled",
        "lineage_snapshot": _snapshot_mapping(source.get("lineage")),
        "identity_snapshot": _snapshot_mapping(source.get("task_identity")),
        "queue_write_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_worker_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_commit_gate_disabled",
    }

"""Disabled queue admission preview for runtime activation.

This module snapshots task identity and lineage metadata only. It does not
import queue implementations, write queue files, create tasks, call scheduler
or executor code, run tools, spawn subprocesses, or mutate runtime/repo state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_queue_admission"]


_TASK_IDENTITY_KEYS = (
    "task_id",
    "task_type",
    "task_name",
    "intent_type",
    "mode",
)

_LINEAGE_KEYS = (
    "lineage_id",
    "parent_id",
    "request_id",
    "activation_id",
    "trace_id",
    "reason",
)


def _snapshot_fields(source: Mapping, keys: tuple[str, ...]) -> dict:
    return {key: source[key] for key in keys if key in source}


def preview_runtime_activation_queue_admission(
    materialization_preview: object = None,
) -> dict:
    """Return a deterministic disabled queue admission preview."""

    is_mapping = isinstance(materialization_preview, Mapping)
    source = materialization_preview if is_mapping else {}

    task_identity = _snapshot_fields(source, _TASK_IDENTITY_KEYS)
    lineage = _snapshot_fields(source, _LINEAGE_KEYS)

    return {
        "enabled": False,
        "mode": "queue_admission_preview",
        "preview_only": True,
        "input_present": materialization_preview is not None,
        "input_type": type(materialization_preview).__name__,
        "input_keys": sorted(str(key) for key in source.keys()),
        "task_identity": dict(sorted(task_identity.items())),
        "lineage": dict(sorted(lineage.items())),
        "queue_admission_ready": True,
        "queue_insert_allowed": False,
        "queue_status": "disabled",
        "admission_reason": "queue_insertion_disabled",
        "runtime_mutation_allowed": False,
        "task_created": False,
        "queue_file_written": False,
        "scheduler_called": False,
        "executor_called": False,
        "tool_execution_allowed": False,
        "subprocess_allowed": False,
        "background_loop_started": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "result": "blocked",
        "reason": "queue_admission_disabled",
    }

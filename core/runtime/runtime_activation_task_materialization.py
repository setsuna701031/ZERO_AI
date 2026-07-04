"""Disabled task materialization preview for runtime activation.

This module creates deterministic preview metadata only. It does not create
tasks, write queues, call scheduler or executor code, run tools, or mutate
runtime or repository state.
"""

from collections.abc import Mapping

__all__ = ["preview_runtime_activation_task_materialization"]


def _preview_input_metadata(intake: object) -> dict:
    if isinstance(intake, Mapping):
        return {
            "input_present": True,
            "input_type": type(intake).__name__,
            "input_keys": sorted(str(key) for key in intake.keys()),
        }
    return {
        "input_present": intake is not None,
        "input_type": type(intake).__name__,
        "input_keys": [],
    }


def preview_runtime_activation_task_materialization(intake: object = None) -> dict:
    """Return a deterministic disabled task materialization preview."""

    metadata = _preview_input_metadata(intake)
    return {
        "enabled": False,
        "mode": "task_materialization_preview",
        "materialization_status": "disabled",
        "task_created": False,
        "queue_write_allowed": False,
        "scheduler_call_allowed": False,
        "executor_call_allowed": False,
        "tool_execution_allowed": False,
        "runtime_state_mutated": False,
        "repo_state_mutated": False,
        "input_present": metadata["input_present"],
        "input_type": metadata["input_type"],
        "input_keys": list(metadata["input_keys"]),
        "preview_only": True,
        "result": "blocked",
        "reason": "task_materialization_disabled",
    }

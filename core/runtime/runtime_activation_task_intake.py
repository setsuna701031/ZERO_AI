"""Data-only task intent intake for runtime activation preflight.

This module accepts task-like intent metadata and forwards only to the executor
no-op admission path. It creates no task, writes no queue, executes no tools,
and mutates no runtime state.
"""

from core.runtime.runtime_activation_executor_noop_admission import (
    prepare_runtime_activation_executor_noop_admission,
)

__all__ = ["prepare_runtime_activation_task_intake"]


def _copy_downstream_activation_result(result: dict) -> dict:
    copied = dict(result)
    copied["bypass_prevention"] = list(copied.get("bypass_prevention", ()))
    scheduler_result = copied.get("scheduler_dry_dispatch_result")
    if isinstance(scheduler_result, dict):
        scheduler_copy = dict(scheduler_result)
        scheduler_copy["bypass_prevention"] = list(
            scheduler_copy.get("bypass_prevention", ())
        )
        dry_wiring_result = scheduler_copy.get("dry_wiring_result")
        if isinstance(dry_wiring_result, dict):
            dry_wiring_copy = dict(dry_wiring_result)
            dry_wiring_copy["bypass_prevention"] = list(
                dry_wiring_copy.get("bypass_prevention", ())
            )
            scheduler_copy["dry_wiring_result"] = dry_wiring_copy
        copied["scheduler_dry_dispatch_result"] = scheduler_copy
    return copied


def prepare_runtime_activation_task_intake(intent: dict | None = None) -> dict:
    """Return a deterministic blocked task intent intake preflight result."""

    downstream_activation_result = _copy_downstream_activation_result(
        prepare_runtime_activation_executor_noop_admission(intent)
    )

    return {
        "enabled": False,
        "mode": "task_intake_preflight",
        "task_intake_checked": True,
        "task_created": False,
        "task_scheduled": False,
        "task_executed": False,
        "activation_forwarded": True,
        "scheduler_called": False,
        "executor_called": False,
        "tool_execution_allowed": False,
        "mutation_allowed": False,
        "runtime_state_mutated": False,
        "intent_present": intent is not None,
        "intent_type": type(intent).__name__,
        "downstream_activation_result": downstream_activation_result,
        "result": "blocked",
        "reason": "activation_not_enabled",
    }

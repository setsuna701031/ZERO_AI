"""Data-only executor no-op admission bridge for runtime activation.

This module performs no executor call, no tool execution, no IO, and no
mutation. It only layers a deterministic blocked/no-op executor admission
result on top of scheduler dry dispatch.
"""

from core.runtime.runtime_activation_scheduler_dry_dispatch import (
    prepare_runtime_activation_scheduler_dry_dispatch,
)

__all__ = ["prepare_runtime_activation_executor_noop_admission"]


_BYPASS_PREVENTION = (
    "no_real_executor_call",
    "no_tool_execution",
    "no_mutation",
    "no_activation_enablement",
)


def _copy_scheduler_dry_dispatch_result(result: dict) -> dict:
    copied = dict(result)
    copied["bypass_prevention"] = list(copied.get("bypass_prevention", ()))
    if isinstance(copied.get("dry_wiring_result"), dict):
        dry_wiring_result = dict(copied["dry_wiring_result"])
        dry_wiring_result["bypass_prevention"] = list(
            dry_wiring_result.get("bypass_prevention", ())
        )
        copied["dry_wiring_result"] = dry_wiring_result
    return copied


def prepare_runtime_activation_executor_noop_admission(
    request: dict | None = None,
) -> dict:
    """Return a deterministic blocked/no-op executor admission result."""

    scheduler_dry_dispatch_result = _copy_scheduler_dry_dispatch_result(
        prepare_runtime_activation_scheduler_dry_dispatch(request)
    )

    return {
        "enabled": False,
        "mode": "executor_noop_admission",
        "activation_enabled": False,
        "scheduler_dry_dispatch_checked": True,
        "scheduler_dry_dispatch_result": scheduler_dry_dispatch_result,
        "executor_admission_checked": True,
        "executor_admitted": False,
        "executor_called": False,
        "executor_noop": True,
        "tool_execution_allowed": False,
        "mutation_allowed": False,
        "runtime_state_mutated": False,
        "repo_mutated": False,
        "request_present": request is not None,
        "request_type": type(request).__name__,
        "bypass_prevention": list(_BYPASS_PREVENTION),
        "execution_result": "blocked",
        "reason": "executor_admission_disabled",
    }

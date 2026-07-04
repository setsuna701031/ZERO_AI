"""Data-only scheduler dry dispatch bridge for runtime activation.

This module performs no scheduler execution, no executor call, no IO, and no
mutation. It only layers a deterministic blocked dispatch result on top of the
activation dry wiring preflight.
"""

from core.runtime.runtime_activation_dry_wiring import (
    prepare_runtime_activation_dry_wiring,
)

__all__ = ["prepare_runtime_activation_scheduler_dry_dispatch"]


_BYPASS_PREVENTION = (
    "no_scheduler_execution",
    "no_executor_call",
    "no_mutation",
    "no_activation_enablement",
)


def prepare_runtime_activation_scheduler_dry_dispatch(
    request: dict | None = None,
) -> dict:
    """Return a deterministic blocked scheduler dry-dispatch result."""

    dry_wiring_result = dict(prepare_runtime_activation_dry_wiring(request))
    dry_wiring_result["bypass_prevention"] = list(
        dry_wiring_result.get("bypass_prevention", ())
    )

    return {
        "enabled": False,
        "mode": "scheduler_dry_dispatch",
        "activation_enabled": False,
        "dry_wiring_checked": True,
        "dry_wiring_result": dry_wiring_result,
        "scheduler_admission_checked": True,
        "scheduler_dispatch_allowed": False,
        "scheduler_executed": False,
        "executor_allowed": False,
        "executor_called": False,
        "mutation_allowed": False,
        "runtime_state_mutated": False,
        "repo_mutated": False,
        "request_present": request is not None,
        "request_type": type(request).__name__,
        "bypass_prevention": list(_BYPASS_PREVENTION),
        "dispatch_result": "blocked",
        "reason": "scheduler_dispatch_disabled",
    }

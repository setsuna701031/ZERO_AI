"""Data-only dry wiring preflight for runtime activation.

This module intentionally performs no IO, no scheduling, no execution, and no
mutation. It only returns a deterministic blocked preflight result.
"""

__all__ = ["prepare_runtime_activation_dry_wiring"]


_BYPASS_PREVENTION = (
    "no_scheduler_dispatch",
    "no_executor_call",
    "no_mutation",
    "no_activation_enablement",
)


def prepare_runtime_activation_dry_wiring(request: dict | None = None) -> dict:
    """Return a deterministic blocked activation dry-wiring preflight result."""

    return {
        "enabled": False,
        "mode": "dry_wiring",
        "activation_enabled": False,
        "dispatch_allowed": False,
        "executor_allowed": False,
        "mutation_allowed": False,
        "runtime_state_mutated": False,
        "repo_mutated": False,
        "adapter_contract_checked": True,
        "adapter_admission_checked": True,
        "adapter_authorization_checked": True,
        "adapter_lifecycle_checked": True,
        "adapter_dry_run_checked": True,
        "request_present": request is not None,
        "request_type": type(request).__name__,
        "bypass_prevention": list(_BYPASS_PREVENTION),
        "result": "blocked",
        "reason": "activation_disabled",
    }

"""Disabled Recovery Runtime coordinator stub."""

__all__ = ["prepare_recovery_runtime_coordinator"]


def prepare_recovery_runtime_coordinator(**_metadata: object) -> dict[str, object]:
    """Return disabled runtime coordinator data."""

    return {
        "enabled": False,
        "runtime_coordinator_status": "stub",
        "pipeline_bound": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

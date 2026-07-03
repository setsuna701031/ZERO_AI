"""Disabled Recovery Runtime execution coordinator stub."""

__all__ = ["prepare_recovery_execution_coordinator"]


def prepare_recovery_execution_coordinator(**_metadata: object) -> dict[str, object]:
    """Return disabled execution coordinator data."""

    return {
        "enabled": False,
        "coordinator_status": "stub",
        "coordination_active": False,
        "execution_allowed": False,
        "recovery_executed": False,
        "runtime_state_mutated": False,
    }

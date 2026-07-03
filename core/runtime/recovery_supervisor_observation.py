"""Disabled Recovery supervisor observation stub."""

__all__ = ["prepare_recovery_supervisor_observation"]


def prepare_recovery_supervisor_observation(**_metadata: object) -> dict[str, object]:
    """Return disabled Recovery supervisor observation data."""

    return {
        "enabled": False,
        "observation_status": "stub",
        "supervisor_bound": False,
        "observation_active": False,
        "recovery_controlled": False,
        "runtime_state_mutated": False,
    }

"""Disabled Recovery Runtime execution dispatcher stub."""

__all__ = ["prepare_recovery_execution_dispatcher"]


def prepare_recovery_execution_dispatcher(**_metadata: object) -> dict[str, object]:
    """Return disabled execution dispatcher data."""

    return {
        "enabled": False,
        "dispatcher_status": "stub",
        "dispatch_allowed": False,
        "execution_allowed": False,
        "recovery_dispatched": False,
        "runtime_state_mutated": False,
    }

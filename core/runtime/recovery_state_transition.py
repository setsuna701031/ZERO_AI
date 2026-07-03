"""Inert Runtime Recovery state transition skeleton."""

__all__ = ["prepare_recovery_state_transition"]


def prepare_recovery_state_transition(**metadata: object) -> dict[str, object]:
    """Return disabled state transition skeleton data without applying transitions."""

    return {
        "enabled": False,
        "transition_status": "skeleton",
        "transition_applied": False,
        "runtime_state_mutated": False,
        "metadata": dict(metadata),
    }

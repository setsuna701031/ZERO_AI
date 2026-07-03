"""Inert Runtime Recovery executor skeleton."""

__all__ = ["prepare_recovery_executor"]


def prepare_recovery_executor(**metadata: object) -> dict[str, object]:
    """Return disabled executor skeleton data without executing recovery."""

    return {
        "enabled": False,
        "executor_status": "skeleton",
        "execution_allowed": False,
        "recovery_executed": False,
        "runtime_state_mutated": False,
        "metadata": dict(metadata),
    }

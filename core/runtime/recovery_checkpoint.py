"""Inert Runtime Recovery checkpoint skeleton."""

__all__ = ["prepare_recovery_checkpoint"]


def prepare_recovery_checkpoint(**metadata: object) -> dict[str, object]:
    """Return disabled checkpoint skeleton data without creating or restoring checkpoints."""

    return {
        "enabled": False,
        "checkpoint_status": "skeleton",
        "checkpoint_created": False,
        "checkpoint_restored": False,
        "runtime_state_mutated": False,
        "metadata": dict(metadata),
    }

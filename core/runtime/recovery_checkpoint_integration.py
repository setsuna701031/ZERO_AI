"""Disabled RecoveryCheckpoint integration stub."""

__all__ = ["prepare_recovery_checkpoint_integration"]


def prepare_recovery_checkpoint_integration(**_metadata: object) -> dict[str, object]:
    """Return disabled RecoveryCheckpoint integration data."""

    return {
        "enabled": False,
        "checkpoint_integration_status": "stub",
        "checkpoint_bound": False,
        "checkpoint_created": False,
        "checkpoint_restored": False,
        "runtime_state_mutated": False,
    }

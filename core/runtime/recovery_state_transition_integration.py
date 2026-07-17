"""Disabled RecoveryStateTransition integration stub."""

__all__ = ["prepare_recovery_state_transition_integration"]


def prepare_recovery_state_transition_integration(**_metadata: object) -> dict[str, object]:
    """Return disabled RecoveryStateTransition integration data."""

    return {
        "enabled": False,
        "state_transition_integration_status": "stub",
        "transition_bound": False,
        "transition_applied": False,
        "runtime_state_mutated": False,
    }

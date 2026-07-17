"""Disabled Recovery Runtime controlled activation projection stub."""

__all__ = ["prepare_recovery_controlled_activation_projection"]


def prepare_recovery_controlled_activation_projection(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation projection metadata."""

    return {
        "enabled": False,
        "projection_status": "stub",
        "activation_status": "disabled",
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
    }

"""Disabled Recovery Runtime controlled activation authorization projection stub."""

__all__ = ["prepare_recovery_controlled_activation_authorization_projection"]


def prepare_recovery_controlled_activation_authorization_projection(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation authorization summary."""

    return {
        "enabled": False,
        "authorization_status": "reserved",
        "authorization_allowed": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
    }

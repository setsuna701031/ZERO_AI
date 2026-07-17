"""Disabled Recovery Runtime controlled activation authorization policy stub."""

__all__ = ["prepare_recovery_controlled_activation_authorization_policy"]


def prepare_recovery_controlled_activation_authorization_policy(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation authorization metadata."""

    return {
        "enabled": False,
        "authorization_status": "reserved",
        "authorization_version": "v1_reserved",
        "authorization_allowed": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

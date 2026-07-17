"""Disabled Recovery Runtime controlled activation grant projection stub."""

__all__ = ["prepare_recovery_controlled_activation_grant_projection"]


def prepare_recovery_controlled_activation_grant_projection(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation grant projection metadata."""

    return {
        "enabled": False,
        "grant_status": "reserved",
        "activation_granted": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

"""Disabled Recovery Runtime controlled activation permit policy stub."""

__all__ = ["prepare_recovery_controlled_activation_permit_policy"]


def prepare_recovery_controlled_activation_permit_policy(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation permit policy metadata."""

    return {
        "enabled": False,
        "permit_status": "reserved",
        "permit_version": "v1_reserved",
        "authorization_status": "disabled",
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

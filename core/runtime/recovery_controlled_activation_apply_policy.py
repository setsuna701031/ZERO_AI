"""Disabled Recovery Runtime controlled activation apply policy stub."""

__all__ = ["prepare_recovery_controlled_activation_apply_policy"]


def prepare_recovery_controlled_activation_apply_policy(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation apply policy metadata."""

    return {
        "enabled": False,
        "apply_status": "reserved",
        "apply_version": "v1_reserved",
        "commit_consumed": False,
        "grant_consumed": False,
        "permit_consumed": False,
        "authorization_confirmed": False,
        "activation_applied": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

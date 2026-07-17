"""Disabled Recovery Runtime controlled activation grant policy stub."""

__all__ = ["prepare_recovery_controlled_activation_grant_policy"]


def prepare_recovery_controlled_activation_grant_policy(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation grant policy metadata."""

    return {
        "enabled": False,
        "grant_status": "reserved",
        "grant_version": "v1_reserved",
        "permit_granted": False,
        "activation_granted": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

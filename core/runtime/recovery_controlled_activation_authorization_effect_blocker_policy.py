"""Disabled Recovery Runtime controlled activation authorization effect blocker policy."""

__all__ = ["prepare_recovery_controlled_activation_authorization_effect_blocker_policy"]


def prepare_recovery_controlled_activation_authorization_effect_blocker_policy(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled authorization effect blocker policy metadata."""

    return {
        "enabled": False,
        "authorization_effect_blocker_status": "reserved",
        "authorization_effect_blocker_version": "v1_reserved",
        "authorization_effect_blocked": True,
        "authorization_effective": False,
        "authorization_escalated": False,
        "execution_grant_created": False,
        "execution_permission_granted": False,
        "runtime_permission_escalated": False,
        "activation_allowed": False,
        "activation_occurred": False,
        "recovery_execution_allowed": False,
        "recovery_executed": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

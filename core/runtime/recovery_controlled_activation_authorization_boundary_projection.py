"""Disabled Recovery Runtime controlled activation authorization boundary projection."""

__all__ = ["prepare_recovery_controlled_activation_authorization_boundary_projection"]


def prepare_recovery_controlled_activation_authorization_boundary_projection(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled authorization boundary projection metadata."""

    return {
        "enabled": False,
        "authorization_boundary_status": "reserved",
        "authorization_boundary_version": "v1_reserved",
        "authorization_boundary_eligible": False,
        "authorization_recorded": False,
        "authorization_effective": False,
        "execution_grant_created": False,
        "execution_permission_granted": False,
        "runtime_permission_escalated": False,
        "activation_allowed": False,
        "activation_occurred": False,
        "recovery_execution_allowed": False,
        "recovery_executed": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
    }

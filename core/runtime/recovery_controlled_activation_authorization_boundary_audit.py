"""Disabled Recovery Runtime controlled activation authorization boundary audit."""

__all__ = ["prepare_recovery_controlled_activation_authorization_boundary_audit"]


def prepare_recovery_controlled_activation_authorization_boundary_audit(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled authorization boundary audit metadata."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "authorization_boundary_took_effect": False,
        "authorization_recorded": False,
        "authorization_effective": False,
        "execution_grant_created": False,
        "execution_permission_granted": False,
        "runtime_permission_escalated": False,
        "activation_occurred": False,
        "recovery_execution_allowed": False,
        "recovery_executed": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

"""Disabled Recovery Runtime controlled activation admission decision audit stub."""

__all__ = ["prepare_recovery_controlled_activation_admission_decision_audit"]


def prepare_recovery_controlled_activation_admission_decision_audit(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled admission decision audit metadata."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "admission_decision_took_effect": False,
        "admission_occurred": False,
        "authorization_effective": False,
        "activation_occurred": False,
        "execution_permission_granted": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

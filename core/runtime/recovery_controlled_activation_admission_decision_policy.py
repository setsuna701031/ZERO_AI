"""Disabled Recovery Runtime controlled activation admission decision policy stub."""

__all__ = ["prepare_recovery_controlled_activation_admission_decision_policy"]


def prepare_recovery_controlled_activation_admission_decision_policy(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled admission decision policy metadata."""

    return {
        "enabled": False,
        "admission_decision_status": "reserved",
        "admission_decision_version": "v1_reserved",
        "admission_decision_eligible": False,
        "admission_decision_recorded": False,
        "admission_decision_effective": False,
        "admission_approved": False,
        "authorization_effective": False,
        "activation_allowed": False,
        "execution_permission_granted": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

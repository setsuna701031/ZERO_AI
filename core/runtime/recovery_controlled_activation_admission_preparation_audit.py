"""Disabled Recovery Runtime controlled activation admission preparation audit stub."""

__all__ = ["prepare_recovery_controlled_activation_admission_preparation_audit"]


def prepare_recovery_controlled_activation_admission_preparation_audit(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled admission preparation audit metadata."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "admission_preparation_occurred": False,
        "admission_occurred": False,
        "authorization_granted": False,
        "activation_occurred": False,
        "execution_occurred": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

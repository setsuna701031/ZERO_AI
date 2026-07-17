"""Disabled Recovery Runtime controlled activation admission preparation projection stub."""

__all__ = ["prepare_recovery_controlled_activation_admission_preparation_projection"]


def prepare_recovery_controlled_activation_admission_preparation_projection(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled admission preparation projection metadata."""

    return {
        "enabled": False,
        "admission_preparation_status": "reserved",
        "admission_preparation_version": "v1_reserved",
        "admission_preparation_eligible": False,
        "admission_preparation_ready": False,
        "admission_prepared": False,
        "admission_allowed": False,
        "authorization_granted": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
    }

"""Disabled Recovery Runtime controlled activation apply audit stub."""

__all__ = ["prepare_recovery_controlled_activation_apply_audit"]


def prepare_recovery_controlled_activation_apply_audit(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation apply audit metadata."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "activation_apply_occurred": False,
        "commit_consumed": False,
        "grant_consumed": False,
        "permit_consumed": False,
        "authorization_confirmed": False,
        "activation_occurred": False,
        "execution_occurred": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

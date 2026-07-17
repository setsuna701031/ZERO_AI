"""Disabled Recovery Runtime controlled activation commit audit stub."""

__all__ = ["prepare_recovery_controlled_activation_commit_audit"]


def prepare_recovery_controlled_activation_commit_audit(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation commit audit metadata."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "activation_commit_occurred": False,
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

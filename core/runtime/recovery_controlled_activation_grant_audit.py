"""Disabled Recovery Runtime controlled activation grant audit stub."""

__all__ = ["prepare_recovery_controlled_activation_grant_audit"]


def prepare_recovery_controlled_activation_grant_audit(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation grant audit metadata."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "grant_issued": False,
        "activation_occurred": False,
        "execution_occurred": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

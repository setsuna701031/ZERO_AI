"""Disabled Recovery Runtime controlled activation permit audit stub."""

__all__ = ["prepare_recovery_controlled_activation_permit_audit"]


def prepare_recovery_controlled_activation_permit_audit(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation permit audit metadata."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "permit_status": "reserved",
        "authorization_status": "disabled",
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "audit_log_written": False,
        "reason": "future_package",
        "metadata": {},
    }

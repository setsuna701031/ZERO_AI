"""Disabled Recovery Runtime controlled activation authorization audit stub."""

__all__ = ["prepare_recovery_controlled_activation_authorization_audit"]


def prepare_recovery_controlled_activation_authorization_audit(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation authorization audit metadata."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "authorization_occurred": False,
        "activation_occurred": False,
        "execution_occurred": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "runtime_wiring_connected": False,
        "historical_modules_connected": False,
        "reason": "future_package",
    }

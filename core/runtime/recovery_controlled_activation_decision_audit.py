"""Disabled Recovery Runtime controlled activation decision audit stub."""

__all__ = ["prepare_recovery_controlled_activation_decision_audit"]


def prepare_recovery_controlled_activation_decision_audit(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation decision audit metadata."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "activation_occurred": False,
        "execution_occurred": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
    }

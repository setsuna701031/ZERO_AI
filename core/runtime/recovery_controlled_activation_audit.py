"""Disabled Recovery Runtime controlled activation audit stub."""

__all__ = ["prepare_recovery_controlled_activation_audit"]


def prepare_recovery_controlled_activation_audit(**_metadata: object) -> dict[str, object]:
    """Return disabled controlled activation audit metadata."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "activation_recorded": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
    }

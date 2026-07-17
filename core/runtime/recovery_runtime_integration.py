"""Disabled Runtime Recovery integration stub."""

__all__ = ["prepare_recovery_runtime_integration"]


def prepare_recovery_runtime_integration(**_metadata: object) -> dict[str, object]:
    """Return disabled Runtime Recovery integration data."""

    return {
        "enabled": False,
        "integration_status": "stub",
        "wiring_active": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

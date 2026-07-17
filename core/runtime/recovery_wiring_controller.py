"""Disabled Runtime Recovery wiring controller stub."""

__all__ = ["prepare_recovery_wiring_controller"]


def prepare_recovery_wiring_controller(**_metadata: object) -> dict[str, object]:
    """Return disabled wiring controller data."""

    return {
        "enabled": False,
        "controller_status": "stub",
        "wiring_allowed": False,
        "activation_bound": False,
        "integration_bound": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

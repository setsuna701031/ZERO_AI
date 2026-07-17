"""Disabled Runtime Recovery wiring status projection stub."""

__all__ = ["prepare_recovery_wiring_status_projection"]


def prepare_recovery_wiring_status_projection(**_metadata: object) -> dict[str, object]:
    """Return disabled wiring status projection data."""

    return {
        "enabled": False,
        "projection_status": "stub",
        "wiring_status": "disabled",
        "activation_status": "disabled",
        "integration_status": "disabled",
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

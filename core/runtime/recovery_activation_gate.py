"""Disabled Runtime Recovery activation gate stub."""

__all__ = ["prepare_recovery_activation_gate"]


def prepare_recovery_activation_gate(**_metadata: object) -> dict[str, object]:
    """Return disabled activation gate data."""

    return {
        "enabled": False,
        "gate_status": "disabled",
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

"""Disabled Recovery Runtime controlled activation gate stub."""

__all__ = ["prepare_recovery_controlled_activation_gate"]


def prepare_recovery_controlled_activation_gate(**_metadata: object) -> dict[str, object]:
    """Return disabled controlled activation gate metadata."""

    return {
        "enabled": False,
        "gate_status": "disabled",
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
    }

"""Disabled Recovery Runtime controlled activation decision projection stub."""

__all__ = ["prepare_recovery_controlled_activation_decision_projection"]


def prepare_recovery_controlled_activation_decision_projection(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation decision projection metadata."""

    return {
        "enabled": False,
        "decision_status": "reserved",
        "decision_version": "v1_reserved",
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
    }

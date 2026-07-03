"""Disabled Recovery Runtime controlled activation decision boundary."""

__all__ = ["prepare_recovery_controlled_activation_decision_boundary"]


def prepare_recovery_controlled_activation_decision_boundary(
    **_reserved_states: object,
) -> dict[str, object]:
    """Return the disabled controlled activation decision boundary summary."""

    return {
        "enabled": False,
        "decision_status": "blocked",
        "activation_allowed": False,
        "authorization_granted": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "controlled_activation_not_enabled",
    }

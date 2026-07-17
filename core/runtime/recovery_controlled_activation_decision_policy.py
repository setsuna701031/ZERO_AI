"""Disabled Recovery Runtime controlled activation decision policy stub."""

__all__ = ["prepare_recovery_controlled_activation_decision_policy"]


def prepare_recovery_controlled_activation_decision_policy(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation decision policy metadata."""

    return {
        "enabled": False,
        "decision_status": "reserved",
        "decision_version": "v1_reserved",
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
        "metadata": {},
    }

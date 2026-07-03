"""Disabled Recovery Runtime controlled activation policy stub."""

__all__ = ["prepare_recovery_controlled_activation_policy"]


def prepare_recovery_controlled_activation_policy(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation policy metadata."""

    return {
        "enabled": False,
        "policy_status": "reserved",
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
    }

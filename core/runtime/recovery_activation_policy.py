"""Disabled Runtime Recovery activation policy stub."""

__all__ = ["prepare_recovery_activation_policy"]


def prepare_recovery_activation_policy(**_metadata: object) -> dict[str, object]:
    """Return reserved activation policy data."""

    return {
        "enabled": False,
        "policy_status": "stub",
        "activation_policy_result": "reserved",
        "activation_allowed": False,
        "execution_allowed": False,
        "runtime_state_mutated": False,
    }

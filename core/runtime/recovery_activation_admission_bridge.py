"""Disabled Runtime Recovery activation admission bridge stub."""

__all__ = ["prepare_recovery_activation_admission_bridge"]


def prepare_recovery_activation_admission_bridge(**_metadata: object) -> dict[str, object]:
    """Return disabled activation admission bridge data."""

    return {
        "enabled": False,
        "bridge_status": "stub",
        "admission_bound": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

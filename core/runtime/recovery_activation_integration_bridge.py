"""Disabled Runtime Recovery activation to integration bridge stub."""

__all__ = ["prepare_recovery_activation_integration_bridge"]


def prepare_recovery_activation_integration_bridge(**_metadata: object) -> dict[str, object]:
    """Return disabled activation to integration bridge data."""

    return {
        "enabled": False,
        "bridge_status": "stub",
        "activation_bound": False,
        "integration_bound": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

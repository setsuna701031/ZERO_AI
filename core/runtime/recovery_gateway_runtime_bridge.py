"""Disabled RecoveryGateway runtime bridge stub."""

__all__ = ["prepare_recovery_gateway_runtime_bridge"]


def prepare_recovery_gateway_runtime_bridge(**_metadata: object) -> dict[str, object]:
    """Return disabled RecoveryGateway runtime bridge data."""

    return {
        "enabled": False,
        "bridge_status": "stub",
        "gateway_bound": False,
        "runtime_bound": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

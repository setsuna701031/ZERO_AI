"""Disabled Recovery Runtime status aggregator stub."""

__all__ = ["prepare_recovery_status_aggregator"]


def prepare_recovery_status_aggregator(**_metadata: object) -> dict[str, object]:
    """Return disabled status aggregation data."""

    return {
        "enabled": False,
        "aggregator_status": "stub",
        "status_projection": "disabled",
        "admission_status": "stub",
        "dispatch_status": "stub",
        "coordination_status": "stub",
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

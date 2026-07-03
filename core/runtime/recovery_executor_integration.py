"""Disabled RecoveryExecutor integration stub."""

__all__ = ["prepare_recovery_executor_integration"]


def prepare_recovery_executor_integration(**_metadata: object) -> dict[str, object]:
    """Return disabled RecoveryExecutor integration data."""

    return {
        "enabled": False,
        "executor_integration_status": "stub",
        "executor_bound": False,
        "execution_allowed": False,
        "recovery_executed": False,
        "runtime_state_mutated": False,
    }

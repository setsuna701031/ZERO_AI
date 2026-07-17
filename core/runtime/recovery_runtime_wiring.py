"""Inert Runtime Recovery wiring skeleton."""

__all__ = ["prepare_recovery_runtime_wiring"]


def prepare_recovery_runtime_wiring(**metadata: object) -> dict[str, object]:
    """Return inert Runtime Recovery wiring data without calling runtime layers."""

    return {
        "enabled": False,
        "wiring_status": "inert",
        "runtime_state_mutated": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "gateway_called": False,
        "executor_called": False,
        "metadata": dict(metadata),
    }

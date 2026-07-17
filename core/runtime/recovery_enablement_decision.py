"""Disabled Recovery Runtime enablement decision stub."""

__all__ = ["prepare_recovery_enablement_decision"]


def prepare_recovery_enablement_decision(**_metadata: object) -> dict[str, object]:
    """Return blocked enablement decision data."""

    return {
        "enabled": False,
        "decision_status": "disabled",
        "decision": "blocked",
        "enablement_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

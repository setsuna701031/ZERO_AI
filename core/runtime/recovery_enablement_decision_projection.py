"""Disabled Recovery Runtime enablement decision projection stub."""

__all__ = ["prepare_recovery_enablement_decision_projection"]


def prepare_recovery_enablement_decision_projection(
    **_metadata: object,
) -> dict[str, object]:
    """Return blocked enablement decision projection data."""

    return {
        "enabled": False,
        "projection_status": "stub",
        "decision_status": "disabled",
        "decision": "blocked",
        "enablement_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

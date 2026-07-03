"""Disabled Recovery Runtime enablement decision audit stub."""

__all__ = ["prepare_recovery_enablement_decision_audit"]


def prepare_recovery_enablement_decision_audit(**_metadata: object) -> dict[str, object]:
    """Return blocked enablement decision audit data."""

    return {
        "enabled": False,
        "audit_status": "stub",
        "decision_recorded": False,
        "decision": "blocked",
        "enablement_allowed": False,
        "execution_allowed": False,
        "runtime_state_mutated": False,
    }

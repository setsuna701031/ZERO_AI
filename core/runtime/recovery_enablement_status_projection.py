"""Disabled Recovery Runtime enablement status projection stub."""

__all__ = ["prepare_recovery_enablement_status_projection"]


def prepare_recovery_enablement_status_projection(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled enablement status projection data."""

    return {
        "enabled": False,
        "projection_status": "stub",
        "enablement_status": "disabled",
        "policy_status": "stub",
        "gate_status": "disabled",
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

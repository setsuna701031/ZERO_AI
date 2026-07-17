"""Disabled Recovery Runtime control pipeline stub."""

__all__ = ["prepare_recovery_control_pipeline"]


def prepare_recovery_control_pipeline(**_metadata: object) -> dict[str, object]:
    """Return disabled control pipeline data."""

    return {
        "enabled": False,
        "pipeline_status": "disabled",
        "enablement_status": "disabled",
        "wiring_status": "disabled",
        "admission_status": "stub",
        "dispatch_status": "stub",
        "coordination_status": "stub",
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

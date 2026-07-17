"""Disabled Recovery Runtime control pipeline status projection stub."""

__all__ = ["prepare_recovery_control_pipeline_status"]


def prepare_recovery_control_pipeline_status(**_metadata: object) -> dict[str, object]:
    """Return disabled control pipeline status projection data."""

    return {
        "enabled": False,
        "projection_status": "stub",
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

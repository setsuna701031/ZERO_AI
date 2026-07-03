"""Disabled Recovery Runtime execution admission stub."""

__all__ = ["prepare_recovery_execution_admission"]


def prepare_recovery_execution_admission(**_metadata: object) -> dict[str, object]:
    """Return disabled execution admission data."""

    return {
        "enabled": False,
        "admission_status": "stub",
        "admission_granted": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

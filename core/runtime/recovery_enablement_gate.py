"""Disabled Recovery Runtime enablement gate stub."""

__all__ = ["prepare_recovery_enablement_gate"]


def prepare_recovery_enablement_gate(**_metadata: object) -> dict[str, object]:
    """Return disabled enablement gate data."""

    return {
        "enabled": False,
        "gate_status": "disabled",
        "enablement_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }

"""Disabled Recovery Runtime enablement policy stub."""

__all__ = ["prepare_recovery_enablement_policy"]


def prepare_recovery_enablement_policy(**_metadata: object) -> dict[str, object]:
    """Return disabled enablement policy data."""

    return {
        "enabled": False,
        "policy_status": "stub",
        "enablement_policy_result": "reserved",
        "enablement_allowed": False,
        "execution_allowed": False,
        "runtime_state_mutated": False,
    }

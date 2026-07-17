"""Disabled Recovery Runtime controlled activation commit projection stub."""

__all__ = ["prepare_recovery_controlled_activation_commit_projection"]


def prepare_recovery_controlled_activation_commit_projection(
    **_metadata: object,
) -> dict[str, object]:
    """Return disabled controlled activation commit projection metadata."""

    return {
        "enabled": False,
        "commit_status": "reserved",
        "commit_version": "v1_reserved",
        "grant_consumed": False,
        "permit_consumed": False,
        "authorization_confirmed": False,
        "activation_committed": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
        "reason": "future_package",
    }

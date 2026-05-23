from __future__ import annotations

import pytest

from core.runtime.runtime_seal import (
    RuntimeSealAuthorityRejected,
    build_runtime_seal_authority_state,
    enforce_runtime_seal_authority,
)


def test_runtime_seal_authority_locks_runtime() -> None:
    state = build_runtime_seal_authority_state(
        freeze_escalated=True,
        session_blocked=True,
        seal_verified=False,
        reason="runtime sovereign lockdown",
    )

    assert state["sovereign_locked"] is True
    assert state["resume_allowed"] is False
    assert state["mutation_allowed"] is False
    assert "freeze_escalated" in state["denial_reasons"]
    assert "runtime_seal_mismatch" in state["denial_reasons"]


def test_runtime_seal_authority_denies_reopen() -> None:
    state = build_runtime_seal_authority_state(
        freeze_escalated=True,
        session_blocked=True,
    )

    with pytest.raises(RuntimeSealAuthorityRejected):
        enforce_runtime_seal_authority(
            state,
            action="replay_reopen",
        )


def test_runtime_seal_authority_allows_clean_runtime() -> None:
    state = build_runtime_seal_authority_state(
        freeze_escalated=False,
        session_blocked=False,
        seal_verified=True,
    )

    result = enforce_runtime_seal_authority(
        state,
        action="runtime_resume",
    )

    assert result["ok"] is True
    assert result["authority_state"]["sovereign_locked"] is False

from __future__ import annotations

import pytest

from core.runtime.runtime_self_protection import (

    RuntimeSelfProtectionState,
    RuntimeUnlockAuthority,
    RuntimeUnlockRejected,
)
pytestmark = [pytest.mark.contract]



def test_runtime_unlock_authority_approves_clean_runtime() -> None:
    authority = RuntimeUnlockAuthority()

    decision = authority.evaluate_unlock(
        seal_verified=True,
        integrity_restored=True,
        rollback_stable=True,
        governance_valid=True,
        constitution_valid=True,
    )

    assert decision.unlock_approved is True
    assert decision.execution_restored is True
    assert decision.sovereign_locked is False


def test_runtime_unlock_authority_denies_locked_runtime() -> None:
    authority = RuntimeUnlockAuthority()

    decision = authority.evaluate_unlock(
        seal_verified=False,
        integrity_restored=True,
        rollback_stable=True,
        governance_valid=True,
        constitution_valid=True,
    )

    assert decision.unlock_approved is False
    assert decision.sovereign_locked is True


def test_runtime_unlock_authority_denies_quarantined_runtime() -> None:
    authority = RuntimeUnlockAuthority()

    with pytest.raises(RuntimeUnlockRejected):
        authority.enforce_unlock(
            seal_verified=True,
            integrity_restored=True,
            rollback_stable=True,
            governance_valid=True,
            constitution_valid=True,
            protection_state=RuntimeSelfProtectionState(
                mutation_frozen=True,
                quarantined_mutations=("mutation-001",),
            ),
        )

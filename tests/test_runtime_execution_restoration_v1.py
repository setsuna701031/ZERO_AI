from __future__ import annotations

import pytest

from core.runtime.runtime_self_protection import (
    RuntimeExecutionRestoration,
    RuntimeSelfProtectionState,
    RuntimeUnlockAuthority,
    RuntimeUnlockRejected,
    restore_runtime_execution,
)


def test_controlled_runtime_execution_restoration() -> None:
    restoration = restore_runtime_execution(
        unlock_authority=RuntimeUnlockAuthority(),
        seal_verified=True,
        integrity_restored=True,
        rollback_stable=True,
        governance_valid=True,
        constitution_valid=True,
    )

    assert isinstance(restoration, RuntimeExecutionRestoration)
    assert restoration.restored is True
    assert restoration.executed is True
    assert restoration.runtime_resumed is True
    assert restoration.unlock_decision["unlock_approved"] is True


def test_controlled_runtime_execution_restoration_denied_when_quarantined() -> None:
    with pytest.raises(RuntimeUnlockRejected):
        restore_runtime_execution(
            unlock_authority=RuntimeUnlockAuthority(),
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

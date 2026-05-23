from __future__ import annotations

import pytest

from core.runtime.runtime_freeze import (
    RuntimeExecutionFrozen,
    RuntimeFreezeAuthority,
    RuntimeFreezeState,
    enforce_runtime_not_frozen,
    evaluate_runtime_freeze,
)


def test_runtime_freeze_authority_allows_unfrozen_runtime() -> None:
    decision = evaluate_runtime_freeze(
        freeze_state={"runtime_frozen": False},
        action_type="read_file",
    )

    assert decision.allowed is True
    assert decision.denied is False
    assert decision.runtime_frozen is False


def test_runtime_freeze_authority_denies_frozen_runtime() -> None:
    decision = evaluate_runtime_freeze(
        freeze_state={
            "runtime_frozen": True,
            "reason": "rollback mismatch",
            "freeze_id": "freeze-001",
            "metadata": {"rollback_id": "rollback-001"},
        },
        action_type="apply_patch",
    )

    assert decision.allowed is False
    assert decision.denied is True
    assert decision.runtime_frozen is True
    assert decision.reason == "rollback mismatch"
    assert decision.freeze_id == "freeze-001"
    assert decision.metadata["rollback_id"] == "rollback-001"


def test_runtime_freeze_authority_enforce_raises_when_frozen() -> None:
    with pytest.raises(RuntimeExecutionFrozen):
        enforce_runtime_not_frozen(
            freeze_state=RuntimeFreezeState(
                runtime_frozen=True,
                reason="runtime locked",
                freeze_id="freeze-002",
            ),
            action_type="governed_repair_transaction",
        )


def test_runtime_freeze_authority_enforce_passes_when_unfrozen() -> None:
    decision = RuntimeFreezeAuthority().enforce(
        freeze_state={"runtime_frozen": False},
        action_type="runtime_status",
    )

    assert decision.allowed is True

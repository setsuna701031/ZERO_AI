from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from core.runtime.governed_repair_execution import execute_governed_repair_transaction


@dataclass(frozen=True)
class FakeGovernanceSnapshot:
    governance_id: str


@dataclass(frozen=True)
class FakeRuntimeConstitution:
    constitution_version: str
    allowed_actions: tuple[str, ...]
    review_required_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]


def _governance() -> FakeGovernanceSnapshot:
    return FakeGovernanceSnapshot(governance_id="governance-snapshot-001")


def test_governed_repair_execution_blocks_before_preflight(tmp_path: Path) -> None:
    constitution = FakeRuntimeConstitution(
        constitution_version="runtime-constitution-v1",
        allowed_actions=(),
        review_required_actions=(),
        blocked_actions=("governed_repair_transaction",),
    )

    with pytest.raises(PermissionError) as exc:
        execute_governed_repair_transaction(
            transaction={"broken": "transaction"},
            workspace_root=tmp_path,
            sandbox_source_root=tmp_path,
            rollback_root=tmp_path,
            report_root=tmp_path,
            allowed_roots=[str(tmp_path)],
            governance_snapshot=_governance(),
            constitution=constitution,
        )

    assert "governed_runtime_execution_blocked" in str(exc.value)


def test_governed_repair_execution_requires_review_before_preflight(tmp_path: Path) -> None:
    constitution = FakeRuntimeConstitution(
        constitution_version="runtime-constitution-v1",
        allowed_actions=(),
        review_required_actions=("governed_repair_transaction",),
        blocked_actions=(),
    )

    with pytest.raises(PermissionError) as exc:
        execute_governed_repair_transaction(
            transaction={"broken": "transaction"},
            workspace_root=tmp_path,
            sandbox_source_root=tmp_path,
            rollback_root=tmp_path,
            report_root=tmp_path,
            allowed_roots=[str(tmp_path)],
            governance_snapshot=_governance(),
            constitution=constitution,
        )

    assert "governed_runtime_execution_requires_review" in str(exc.value)

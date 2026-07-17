from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from core.runtime.mutation_runtime_pipeline import run_mutation_runtime_pipeline


@dataclass(frozen=True)
class FakeRiskLevel:
    value: str = "medium"


@dataclass(frozen=True)
class FakeSession:
    session_id: str = "session-001"
    intent: str = "test mutation runtime pipeline"
    approval_mode: object = type("ApprovalMode", (), {"value": "review_required"})()
    verification: object = type("Verification", (), {"value": "targeted_tests"})()
    risk_level: object = FakeRiskLevel()
    initiator: str = "test"


@dataclass(frozen=True)
class FakeGovernanceSnapshot:
    governance_id: str


@dataclass(frozen=True)
class FakeRuntimeConstitution:
    constitution_version: str
    allowed_actions: tuple[str, ...]
    review_required_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]


def test_mutation_runtime_pipeline_freeze_blocks_before_reports(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"

    with pytest.raises(PermissionError) as exc:
        run_mutation_runtime_pipeline(
            session=FakeSession(),
            relative_paths=["a.py"],
            workspace_root=tmp_path,
            sandbox_source_root=tmp_path,
            rollback_root=tmp_path,
            report_root=report_root,
            freeze_state={
                "runtime_frozen": True,
                "reason": "rollback verification mismatch",
                "freeze_id": "freeze-001",
            },
        )

    assert "mutation_runtime_pipeline_frozen" in str(exc.value)
    assert not report_root.exists()


def test_mutation_runtime_pipeline_legality_blocks_before_reports(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    constitution = FakeRuntimeConstitution(
        constitution_version="runtime-constitution-v1",
        allowed_actions=(),
        review_required_actions=(),
        blocked_actions=("mutation_runtime_pipeline",),
    )

    with pytest.raises(PermissionError) as exc:
        run_mutation_runtime_pipeline(
            session=FakeSession(),
            relative_paths=["a.py"],
            workspace_root=tmp_path,
            sandbox_source_root=tmp_path,
            rollback_root=tmp_path,
            report_root=report_root,
            governance_snapshot=FakeGovernanceSnapshot("governance-001"),
            constitution=constitution,
        )

    assert "mutation_runtime_pipeline_blocked" in str(exc.value)
    assert not report_root.exists()


def test_mutation_runtime_pipeline_legality_review_blocks_before_reports(tmp_path: Path) -> None:
    report_root = tmp_path / "reports"
    constitution = FakeRuntimeConstitution(
        constitution_version="runtime-constitution-v1",
        allowed_actions=(),
        review_required_actions=("mutation_runtime_pipeline",),
        blocked_actions=(),
    )

    with pytest.raises(PermissionError) as exc:
        run_mutation_runtime_pipeline(
            session=FakeSession(),
            relative_paths=["a.py"],
            workspace_root=tmp_path,
            sandbox_source_root=tmp_path,
            rollback_root=tmp_path,
            report_root=report_root,
            governance_snapshot=FakeGovernanceSnapshot("governance-001"),
            constitution=constitution,
        )

    assert "mutation_runtime_pipeline_requires_review" in str(exc.value)
    assert not report_root.exists()

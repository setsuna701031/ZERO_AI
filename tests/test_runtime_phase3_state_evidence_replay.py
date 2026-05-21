from __future__ import annotations

from pathlib import Path

import pytest

from core.runtime import mutation_patch_apply
from core.runtime.governed_mutation_runtime import run_governed_mutation_runtime
from core.runtime.mutation_gateway import MutationGatewayRequest
from core.runtime.mutation_patch_apply import MutationPatchApplyResult
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationScope,
    MutationVerificationRequirement,
)
from core.runtime.mutation_verification import MutationVerificationCheck
from core.runtime.runtime_kernel_state import RuntimeKernelStateMachine


def _request(
    *,
    workspace: Path,
    sandbox: Path,
    rollback: Path,
    reports: Path,
    verification_passed: bool = True,
) -> MutationGatewayRequest:
    return MutationGatewayRequest(
        intent="Update runtime demo",
        initiator="test",
        reason="phase 3 runtime topology",
        relative_paths=("core/runtime/demo.py",),
        scope=MutationScope(allowed_paths=("core/runtime",)),
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.TARGETED_TESTS,
        verification_checks=(
            MutationVerificationCheck(
                name="pytest",
                passed=verification_passed,
                details="ok" if verification_passed else "boom",
            ),
        ),
    )


def test_kernel_state_machine_rejects_invalid_transition_and_restores_checkpoint() -> None:
    machine = RuntimeKernelStateMachine()
    first = machine.checkpoint({"marker": "start"})

    with pytest.raises(ValueError):
        machine.transition("COMMITTING", reason="skip lifecycle")

    machine.transition("SCANNING", reason="scan")
    machine.restore(first.checkpoint_id)

    assert machine.state == "PENDING"


def test_governed_runtime_attaches_evidence_bundle_replay_and_state_progression(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    target = workspace / "core" / "runtime" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VERSION = 1\n", encoding="utf-8")

    source = sandbox / "core" / "runtime" / "demo.py"
    source.parent.mkdir(parents=True)
    source.write_text("VERSION = 2\n", encoding="utf-8")

    result = run_governed_mutation_runtime(
        _request(
            workspace=workspace,
            sandbox=sandbox,
            rollback=rollback,
            reports=reports,
        )
    )
    payload = result.to_dict()

    states = [
        item["new_state"]
        for item in payload["runtime_evidence_bundle"]["runtime_state_transitions"]
    ]

    assert states == [
        "SCANNING",
        "PLANNING",
        "APPLYING",
        "VERIFYING",
        "COMMITTING",
        "REPLAYING",
        "FINALIZED",
    ]
    assert payload["runtime_evidence_bundle"]["stdout"] == "ok"
    assert payload["runtime_replay"]["state_progression"]
    assert payload["runtime_replay"]["impacted_plan"]["changed_files"] == [
        "core/runtime/demo.py"
    ]
    assert Path(payload["artifact_paths"]["evidence_bundle"]).exists()


def test_governed_runtime_rolls_back_full_transaction_on_apply_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    target = workspace / "core" / "runtime" / "demo.py"
    target.parent.mkdir(parents=True)
    target.write_text("VERSION = 1\n", encoding="utf-8")

    def partial_apply(**kwargs):
        target.write_text("BROKEN = True\n", encoding="utf-8")
        raise RuntimeError("simulated partial apply failure")

    monkeypatch.setattr(mutation_patch_apply, "apply_patch_plan", partial_apply)

    result = run_governed_mutation_runtime(
        _request(
            workspace=workspace,
            sandbox=sandbox,
            rollback=rollback,
            reports=reports,
        )
    )
    payload = result.to_dict()

    assert payload["failed"] is True
    assert payload["rolled_back"] is True
    assert payload["rollback_snapshot"]["rollback_source"] == "transaction_snapshot"
    assert target.read_text(encoding="utf-8") == "VERSION = 1\n"
    assert "ROLLING_BACK" in [
        item["new_state"]
        for item in payload["runtime_evidence_bundle"]["runtime_state_transitions"]
    ]

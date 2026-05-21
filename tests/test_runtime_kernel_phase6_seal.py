from __future__ import annotations

from pathlib import Path

from core.runtime.governed_mutation_runtime import run_governed_mutation_runtime
from core.runtime.mutation_gateway import MutationGatewayRequest
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationScope,
    MutationVerificationRequirement,
)
from core.runtime.mutation_verification import MutationVerificationCheck
from core.runtime.runtime_abi import validate_abi
from core.runtime.runtime_compatibility import check_runtime_compatibility
from core.runtime.runtime_diagnostics import runtime_diagnostics
from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle
from core.runtime.runtime_events import RuntimeStateTransitionEvent
from core.runtime.runtime_execution_result import RuntimeExecutionResult
from core.runtime.runtime_integrity import RuntimeIntegrityReport
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_replay_session import RuntimeReplaySession
from core.runtime.runtime_seal import seal_runtime_artifact, verify_runtime_seal
from core.runtime.runtime_self_protection import RuntimeSelfProtectionController
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


def test_runtime_seal_snapshot_verifies_and_detects_tamper() -> None:
    payload = {
        "runtime_version": RUNTIME_KERNEL_VERSION,
        "abi_version": RUNTIME_ABI_VERSION,
        "state": {"phase": "seal"},
    }
    seal = seal_runtime_artifact(payload, artifact_type="runtime_seal_snapshot").to_dict()
    sealed = {**payload, "runtime_seal": seal}

    assert verify_runtime_seal(sealed, artifact_type="runtime_seal_snapshot").verified is True

    sealed["state"]["phase"] = "tampered"
    report = verify_runtime_seal(sealed, artifact_type="runtime_seal_snapshot")
    assert report.verified is False
    assert report.reason == "runtime_seal_mismatch"


def test_wal_replay_and_evidence_integrity_detect_tamper() -> None:
    journal = RuntimeJournal()
    journal.append_event(
        RuntimeStateTransitionEvent(
            old_state="PENDING",
            new_state="SCANNING",
            reason="scan",
        )
    )
    assert journal.verify_integrity().verified is True

    record = journal.records[0]
    record.payload["payload"]["reason"] = "tampered"  # type: ignore[index]
    assert journal.verify_integrity().verified is False

    clean_journal = RuntimeJournal()
    clean_journal.append_event(
        RuntimeStateTransitionEvent(
            old_state="PENDING",
            new_state="SCANNING",
            reason="scan",
        )
    )
    replay = RuntimeReplaySession(clean_journal, replay_id="replay:seal").reconstruct().to_dict()
    assert verify_runtime_seal(replay, artifact_type="runtime_replay_artifact").verified is True
    replay["journal_records"][0]["record_type"] = "tampered"
    assert verify_runtime_seal(replay, artifact_type="runtime_replay_artifact").verified is False

    execution = RuntimeExecutionResult(
        execution_id="exec:1",
        execution_start_id="start:1",
        execution_type="phase6",
        status="succeeded",
        started_at="2026-05-21T00:00:00+00:00",
        finished_at="2026-05-21T00:00:01+00:00",
        stdout="ok",
        stderr="",
        return_code=0,
        side_effects=(),
        artifacts=(),
        verified=True,
        blocked=False,
        rollback_required=False,
        lineage={},
        replay_id="replay:seal",
        repair_session_id=None,
        evidence={"stdout": "ok"},
    )
    evidence = RuntimeEvidenceBundle.from_runtime_execution(
        bundle_id="bundle:seal",
        execution_result=execution,
    ).to_dict()
    assert verify_runtime_seal(evidence, artifact_type="runtime_evidence_bundle").verified is True
    evidence["execution_result"]["stdout"] = "tampered"
    assert verify_runtime_seal(evidence, artifact_type="runtime_evidence_bundle").verified is False


def test_abi_versioning_and_compatibility_safe_fail() -> None:
    result = RuntimeExecutionResult(
        execution_id="exec:abi",
        execution_start_id="start:abi",
        execution_type="phase6",
        status="blocked",
        started_at="2026-05-21T00:00:00+00:00",
        finished_at="2026-05-21T00:00:00+00:00",
        stdout="",
        stderr="blocked",
        return_code=1,
        side_effects=(),
        artifacts=(),
        verified=False,
        blocked=True,
        rollback_required=False,
        lineage={},
        replay_id=None,
        repair_session_id=None,
        evidence={"reason": "blocked"},
        executed=False,
    ).to_dict()

    assert validate_abi("runtime_execution_result", result).valid is True
    assert check_runtime_compatibility(result, artifact_type="runtime_execution_result").compatible is True

    incompatible = {**result, "abi_version": "99.0"}
    report = check_runtime_compatibility(incompatible, artifact_type="runtime_execution_result")
    assert report.compatible is False
    assert report.migration_required is True

    missing_version = dict(result)
    missing_version.pop("runtime_version")
    assert check_runtime_compatibility(missing_version).compatible is False


def test_observability_summaries_are_machine_readable() -> None:
    journal = RuntimeJournal()
    journal.append("runtime_memory_snapshot", payload={"snapshot_id": "mem:1"})

    diagnostics = runtime_diagnostics(journal=journal, state={"state": "PENDING"})

    assert diagnostics["runtime"]["runtime_version"] == RUNTIME_KERNEL_VERSION
    assert diagnostics["wal"]["record_count"] == 1
    assert diagnostics["wal"]["integrity"][0]["verified"] is True
    assert diagnostics["abi"]["runtime_wal_record"]["version"] == RUNTIME_ABI_VERSION


def test_self_protection_quarantines_integrity_failure_and_returns_blocked_result() -> None:
    controller = RuntimeSelfProtectionController(max_recursive_repair=0)
    decision = controller.observe_intent(category="recursive repair", mutation_id="mutation:1")

    assert decision.blocked is True
    assert decision.quarantined is True

    failed_integrity = RuntimeIntegrityReport(
        artifact_type="runtime_wal_record",
        verified=False,
        reason="integrity_hash_mismatch",
    )
    freeze = controller.enforce_integrity((failed_integrity,), mutation_id="mutation:2")
    blocked = controller.blocked_result(freeze, execution_id="exec:blocked")

    assert freeze.frozen is True
    assert blocked.to_dict()["status"] == "blocked"
    assert blocked.to_dict()["blocked"] is True
    assert blocked.to_dict()["evidence"]["protection"]["action"] == "quarantine_mutation"


def test_governed_runtime_emits_phase6_seal_diagnostics_and_contract_reports(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"

    target = workspace / "core" / "runtime" / "sealed.py"
    source = sandbox / "core" / "runtime" / "sealed.py"
    target.parent.mkdir(parents=True)
    source.parent.mkdir(parents=True)
    target.write_text("VERSION = 1\n", encoding="utf-8")
    source.write_text("VERSION = 2\n", encoding="utf-8")

    result = run_governed_mutation_runtime(
        MutationGatewayRequest(
            intent="Update runtime sealed kernel file",
            initiator="test",
            reason="phase 6 seal regression",
            relative_paths=("core/runtime/sealed.py",),
            scope=MutationScope(allowed_paths=("core/runtime",)),
            workspace_root=workspace,
            sandbox_source_root=sandbox,
            rollback_root=rollback,
            report_root=reports,
            approval_mode=MutationApprovalMode.AUTO,
            verification=MutationVerificationRequirement.TARGETED_TESTS,
            verification_checks=(
                MutationVerificationCheck(name="pytest", passed=True, details="ok"),
            ),
        )
    )
    payload = result.to_dict()

    assert payload["runtime_evidence_bundle"]["runtime_seal"]
    assert payload["runtime_replay"]["runtime_seal"]
    assert payload["runtime_diagnostics"]["wal"]["record_count"] > 0
    assert payload["runtime_topology"]["evidence"]["sealed"] is True
    assert any(report["verified"] for report in payload["evidence"]["runtime_integrity"])
    assert all(report["compatible"] for report in payload["evidence"]["runtime_compatibility"])
    assert Path(payload["artifact_paths"]["runtime_diagnostics"]).exists()

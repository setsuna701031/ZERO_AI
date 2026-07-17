from __future__ import annotations

from dataclasses import replace
import sys
from pathlib import Path

import pytest

from core.runtime.execution_gateway import safe_subprocess_run
from core.runtime.executor import Executor
from core.runtime.governed_cross_session_handoff_contract import (

    build_governed_cross_session_handoff_contract,
    validate_governed_cross_session_handoff_contract,
)
from core.runtime.governed_runtime_continuation_session import (
    build_governed_runtime_continuation_record,
    validate_governed_runtime_continuation_record,
)
from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationVerificationRequirement,
)
from core.runtime.repair_transaction_execution_bridge import (
    execute_committed_runtime_repair_transaction,
)
from core.runtime.runtime_evidence_chain import validate_runtime_evidence_record
from core.runtime.runtime_execution_request import RuntimeExecutionRequest
from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
from core.runtime.runtime_governance_chain_seal import (
    build_runtime_governance_chain_seal_report,
    validate_runtime_governance_chain_seal_report,
)
from core.runtime.runtime_recovery_coordinator import (
    RuntimeRecoveryCoordinator,
    RuntimeRecoveryRejected,
)
from core.tasks.runtime_repair_transaction import (
    commit_runtime_repair_transaction,
    create_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)
pytestmark = [pytest.mark.integration]



def test_runtime_topology_freeze_gate_preserves_governed_lineage(tmp_path: Path) -> None:
    execution = Executor(workspace_root=tmp_path / "executor").execute_request(
        RuntimeExecutionRequest(
            execution_type="subprocess",
            command=(sys.executable, "-c", "print('freeze-gate')"),
            working_directory=str(tmp_path),
            timeout=20,
            metadata={
                "operation": "runtime_topology_freeze_gate",
                "runtime_identity": {
                    "identity_id": "system:freeze_gate",
                    "identity_type": "SYSTEM",
                    "source": "tests",
                },
                "authority_scope_id": "authority:freeze_gate",
                "capability_scope_id": "capability:freeze_gate",
                "provenance": {"test": "runtime_topology_freeze_gate"},
            },
            lineage={
                "request_id": "freeze-gate-request",
                "execution_start_id": "execution_start:freeze-gate",
            },
            replay_id="replay:freeze-gate",
        )
    )

    assert execution.status == "succeeded"
    metadata = execution.metadata
    evidence = metadata["runtime_evidence_record"]
    audit = metadata["runtime_audit_metadata"]
    authority = evidence["authority_metadata"]
    execution_session = metadata["governed_runtime_execution_session"]
    replay_session = metadata["governed_runtime_replay_session"]

    assert metadata["governed_runtime_boundary_evaluated"] is True
    assert metadata["governed_runtime_owner"] == "core.runtime.executor"
    assert authority["runtime_identity"]["identity_type"] == "SYSTEM"
    assert authority["authority_scope_id"] == "authority:freeze_gate"
    assert validate_runtime_evidence_record(evidence)["ok"] is True
    assert evidence["source_execution_id"] == execution.execution_id
    assert evidence["execution_session_id"] == metadata["governed_runtime_execution_session_id"]
    assert evidence["replay_session_id"] == metadata["governed_runtime_replay_session_id"]
    assert audit["evidence_id"] == evidence["evidence_id"]
    assert audit["execution_session_id"] == evidence["execution_session_id"]
    assert audit["replay_session_id"] == evidence["replay_session_id"]

    assert execution.side_effects
    side_effect = execution.side_effects[0]
    assert side_effect.effect_type == "subprocess"
    assert side_effect.metadata["runtime_evidence_id"] == evidence["evidence_id"]
    assert side_effect.metadata["runtime_audit_metadata"]["evidence_id"] == evidence["evidence_id"]
    assert side_effect.metadata["runtime_audit_metadata"]["execution_session_id"] == (
        evidence["execution_session_id"]
    )

    repair_result = _run_repair_transaction(tmp_path)
    repair_metadata = repair_result.audit_record.metadata
    repair_evidence = repair_metadata["runtime_evidence_record"]
    repair_audit = repair_metadata["runtime_audit_metadata"]
    assert repair_result.completed is True
    assert validate_runtime_evidence_record(repair_evidence)["ok"] is True
    assert repair_metadata["runtime_evidence_id"] == repair_evidence["evidence_id"]
    assert repair_audit["evidence_id"] == repair_evidence["evidence_id"]
    assert repair_audit["mutation_transaction_id"] == repair_evidence["mutation_transaction_id"]
    assert repair_audit["mutation_request_id"] == repair_evidence["mutation_request_id"]
    assert repair_evidence["authority_metadata"]["repair_authority_governance"]["scope_allowed"] is True

    recovery = _verified_recovery_from_repair_lineage(
        repair_metadata,
        execution_session_id=execution_session["execution_session_id"],
    )
    recovery_evidence = recovery.governance["runtime_evidence_record"]
    assert validate_runtime_evidence_record(recovery_evidence)["ok"] is True
    assert recovery.governance["runtime_evidence_id"] == recovery_evidence["evidence_id"]
    assert recovery.governance["runtime_audit_metadata"]["evidence_id"] == recovery_evidence["evidence_id"]
    assert recovery.governance["mutation_transaction_id"] == repair_evidence["mutation_transaction_id"]
    assert recovery.governance["mutation_request_id"] == repair_evidence["mutation_request_id"]
    assert recovery.governance["raw_recovery_execution_allowed"] is False

    continuation = build_governed_runtime_continuation_record(
        source_session_id=execution_session["execution_session_id"],
        replay_session_id=replay_session["replay_session_id"],
    )
    continuation_validation = validate_governed_runtime_continuation_record(continuation)
    assert continuation_validation["continuation_valid"] is True
    assert continuation["lineage_chain"][0] == execution_session["execution_session_id"]
    assert replay_session["replay_session_id"] in continuation["lineage_chain"]

    closure = build_runtime_governance_chain_seal_report(
        boundary_report={
            "boundary_id": "freeze-boundary",
            "boundary_state": "boundary_ready",
            "execution_intent": "runtime_topology_freeze_gate",
            "capability_grant_state": "grant_valid",
            "approval_state": "approval_valid",
            "transaction_state": "sealed",
            "transition_valid": True,
            "rollback_state": "rollback_ready",
            "verification_state": "verification_passed",
            "seal_state": "seal_ready",
            "replay_consistency_state": "replay_consistent",
            "evidence_chain_valid": True,
            "evidence_integrity_state": "valid",
            "replay_evidence_consistent": True,
            "evidence_tamper_detected": False,
            "evidence_seal_valid": True,
            "reconstruction_state": "consistent",
            "reconstruction_consistent": True,
            "replay_order_valid": True,
            "reconstruction_divergence_detected": False,
            "rollback_reconstruction_valid": True,
            "seal_reconstruction_valid": True,
            "blocking_issues": [],
            "reason_codes": [],
        }
    )
    assert validate_runtime_governance_chain_seal_report(closure)["ok"] is True
    assert closure["governance_chain_sealable"] is True

    handoff = build_governed_cross_session_handoff_contract(
        continuation_record=continuation,
        replay_session_report=replay_session,
        execution_session_report=execution_session,
        governance_closure_report={
            "closure_ready": closure["governance_chain_sealable"],
            "closure_state": closure["governance_chain_state"],
            "runtime_governance_freeze_candidate": True,
            "reason_codes": closure["seal_summary"]["reason_codes"],
        },
    )
    assert validate_governed_cross_session_handoff_contract(handoff)["ok"] is True
    assert handoff["handoff_state"] == "ready"
    assert handoff["lineage_valid"] is True
    assert handoff["source_session_id"] == execution_session["execution_session_id"]
    assert handoff["source_replay_session_id"] == replay_session["replay_session_id"]

    facade = safe_subprocess_run(
        (sys.executable, "-c", "print('freeze-facade')"),
        cwd=str(tmp_path),
        timeout=20,
    )
    assert facade["ok"] is True
    facade_metadata = facade["metadata"]
    assert facade_metadata["governed_runtime_boundary_evaluated"] is True
    assert facade_metadata["runtime_evidence_id"] == (
        facade_metadata["runtime_evidence_record"]["evidence_id"]
    )
    assert facade_metadata["runtime_audit_metadata"]["evidence_id"] == (
        facade_metadata["runtime_evidence_id"]
    )
    assert facade_metadata["runtime_audit_metadata"]["execution_session_id"] == (
        facade_metadata["governed_runtime_execution_session_id"]
    )


def test_runtime_topology_freeze_gate_rejects_recovery_without_governed_lineage() -> None:
    coordinator = _coordinator_with_failed_source()
    coordinator.create_recovery("recovery-freeze", "source-freeze")
    replayed = coordinator.run_recovery("recovery-freeze")

    coordinator._recoveries["recovery-freeze"] = replace(
        replayed,
        governance={
            "runtime_evidence_id": "",
            "runtime_evidence_record": {},
            "runtime_audit_metadata": {},
            "authority_metadata": {},
            "execution_session_id": "",
            "replay_session_id": "",
            "mutation_transaction_id": "",
            "mutation_request_id": "",
            "repair_transaction_id": "",
            "raw_recovery_execution_allowed": True,
        },
    )

    with pytest.raises(RuntimeRecoveryRejected):
        coordinator.verify_recovery("recovery-freeze")


def _run_repair_transaction(tmp_path: Path):
    workspace = tmp_path / "repair_workspace"
    sandbox = tmp_path / "repair_sandbox"
    rollback = tmp_path / "repair_rollback"
    reports = tmp_path / "repair_reports"
    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    transaction = create_runtime_repair_transaction(
        task_id="freeze_task",
        proposal_id="freeze_proposal",
        goal="prove repair transaction lineage for runtime topology freeze",
        scope_gate={"scope_allowed": True},
    )
    staged = stage_runtime_repair_mutation(
        transaction,
        {
            "op_type": "write_file",
            "target_path": "project/freeze_gate.py",
            "content": "print('repair freeze gate')\n",
        },
    )
    committed = commit_runtime_repair_transaction(staged)

    return execute_committed_runtime_repair_transaction(
        committed,
        workspace_root=workspace,
        sandbox_source_root=sandbox,
        rollback_root=rollback,
        report_root=reports,
        allowed_roots=("project",),
        approval_mode=MutationApprovalMode.AUTO,
        verification=MutationVerificationRequirement.NONE,
    )


def _verified_recovery_from_repair_lineage(
    repair_metadata: dict,
    *,
    execution_session_id: str,
):
    coordinator = _coordinator_with_failed_source(source_session_id=execution_session_id)
    repair_audit = repair_metadata["runtime_audit_metadata"]
    repair_evidence = repair_metadata["runtime_evidence_record"]
    coordinator.create_recovery(
        "recovery-freeze",
        execution_session_id,
        metadata={
            "lineage": {
                "mutation_transaction_id": repair_evidence["mutation_transaction_id"],
                "mutation_request_id": repair_evidence["mutation_request_id"],
                "repair_transaction_id": repair_audit["mutation_transaction_id"],
                "continuation_id": "continuation:freeze",
                "handoff_id": "handoff:freeze",
            },
            "authority": {"operator": "runtime_topology_freeze_gate"},
            "audit_id": "audit:recovery-freeze",
        },
    )
    coordinator.run_recovery("recovery-freeze")
    return coordinator.verify_recovery("recovery-freeze")


def _coordinator_with_failed_source(
    source_session_id: str = "source-freeze",
) -> RuntimeRecoveryCoordinator:
    manager = RuntimeExecutionSessionManager()
    manager.create_session(source_session_id, f"{source_session_id}:lifecycle")
    manager.start_session(source_session_id)
    manager.fail_session(source_session_id)
    return RuntimeRecoveryCoordinator(session_manager=manager)

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.runtime.mutation_session import (
    MutationApprovalMode,
    MutationVerificationRequirement,
)
from core.runtime.repair_transaction_execution_bridge import (
    execute_committed_runtime_repair_transaction,
)
from core.runtime.runtime_evidence_chain import validate_runtime_evidence_record
from core.tasks.runtime_repair_transaction import (
    commit_runtime_repair_transaction,
    create_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SELF_EDIT_DOC = REPO_ROOT / "docs" / "governed_self_edit_upper_layer.md"
MAINLINE_FREEZE_TEST = REPO_ROOT / "tests" / "test_runtime_mainline_freeze_contract.py"
TOPOLOGY_FREEZE_TEST = REPO_ROOT / "tests" / "test_runtime_topology_freeze_gate.py"

REQUIRED_SELF_EDIT_SPINE = (
    "governed_repair_transaction",
    "mutation_runtime_pipeline",
    "governed_execution",
)


def test_governed_self_edit_document_records_required_runtime_spine() -> None:
    text = SELF_EDIT_DOC.read_text(encoding="utf-8")

    for phrase in (
        "governed repair transaction",
        "mutation request",
        "governed execution",
        "sealed evidence",
        "verification",
        "replay/recovery eligibility",
        "rollback eligibility",
        "Self-edit may request work",
        "autonomous self-edit remains recommendation-only or review-required",
    ):
        assert phrase in text

    assert MAINLINE_FREEZE_TEST.exists()
    assert TOPOLOGY_FREEZE_TEST.exists()


def test_governed_self_edit_success_requires_repair_mutation_runtime_lineage(
    tmp_path: Path,
) -> None:
    result = _run_governed_self_edit_shaped_repair(tmp_path)
    success = _self_edit_success_payload_from_governed_result(result)

    assert _is_governed_self_edit_success(success) is True

    metadata = result.audit_record.metadata
    evidence = metadata["runtime_evidence_record"]
    audit = metadata["runtime_audit_metadata"]

    assert validate_runtime_evidence_record(evidence)["ok"] is True
    assert success["runtime_evidence_id"] == evidence["evidence_id"]
    assert audit["evidence_id"] == evidence["evidence_id"]
    assert audit["mutation_transaction_id"] == evidence["mutation_transaction_id"]
    assert audit["mutation_request_id"] == evidence["mutation_request_id"]
    assert evidence["authority_metadata"]["repair_authority_governance"]["scope_allowed"] is True
    assert success["verification_result"]["status"] == "passed"
    assert success["rollback_recovery_eligibility"]["rollback_state"] == "rollback_ready"
    assert success["rollback_recovery_eligibility"]["recovery_lineage_required"] is True


def test_raw_or_direct_mutation_shapes_are_not_governed_self_edit_success() -> None:
    raw_file_write = {
        "self_edit_state": "succeeded",
        "style": "raw_file_write",
        "path": "core/runtime/example.py",
        "written": True,
    }
    raw_subprocess = {
        "self_edit_state": "succeeded",
        "style": "raw_subprocess",
        "command": "python -c \"print('edited')\"",
        "returncode": 0,
    }
    direct_mutation = {
        "self_edit_state": "succeeded",
        "style": "direct_mutation",
        "transaction": {"status": "committed"},
        "verified": True,
        "rollback_metadata": {"rollback_compatible": True},
    }
    partial_governed_shape = {
        "self_edit_state": "succeeded",
        "runtime_spine": REQUIRED_SELF_EDIT_SPINE,
        "authority_metadata": {"operator": "test"},
        "runtime_evidence_id": "evidence-1",
        "runtime_audit_metadata": {"evidence_id": "evidence-1"},
        "verification_result": {"status": "passed"},
        "rollback_recovery_eligibility": {"rollback_state": "rollback_ready"},
    }

    for payload in (
        raw_file_write,
        raw_subprocess,
        direct_mutation,
        partial_governed_shape,
    ):
        assert _is_governed_self_edit_success(payload) is False


def _run_governed_self_edit_shaped_repair(tmp_path: Path) -> Any:
    workspace = tmp_path / "workspace"
    sandbox = tmp_path / "sandbox"
    rollback = tmp_path / "rollback"
    reports = tmp_path / "reports"
    workspace.mkdir()
    sandbox.mkdir()
    rollback.mkdir()
    reports.mkdir()

    transaction = create_runtime_repair_transaction(
        task_id="self_edit_gate_task",
        proposal_id="self_edit_gate_proposal",
        goal="prove governed self-edit gate requires runtime spine",
        scope_gate={"scope_allowed": True},
        metadata={"source": "governed_self_edit_gate_contract"},
    )
    staged = stage_runtime_repair_mutation(
        transaction,
        {
            "op_type": "write_file",
            "target_path": "project/self_edit_gate.py",
            "content": "print('governed self-edit gate')\n",
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


def _self_edit_success_payload_from_governed_result(result: Any) -> dict[str, Any]:
    metadata = result.audit_record.metadata
    evidence = metadata["runtime_evidence_record"]
    audit = metadata["runtime_audit_metadata"]
    return {
        "self_edit_state": "succeeded",
        "runtime_spine": REQUIRED_SELF_EDIT_SPINE,
        "authority_metadata": evidence.get("authority_metadata"),
        "runtime_evidence_id": metadata.get("runtime_evidence_id"),
        "runtime_audit_metadata": audit,
        "repair_or_mutation_lineage": audit.get("lineage"),
        "verification_result": result.verification.to_dict(),
        "rollback_recovery_eligibility": {
            "rollback_state": evidence.get("rollback_state"),
            "replay_session_id": evidence.get("replay_session_id"),
            "recovery_lineage_required": True,
        },
    }


def _is_governed_self_edit_success(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("self_edit_state") != "succeeded":
        return False
    if tuple(payload.get("runtime_spine") or ()) != REQUIRED_SELF_EDIT_SPINE:
        return False

    authority = payload.get("authority_metadata")
    audit = payload.get("runtime_audit_metadata")
    lineage = payload.get("repair_or_mutation_lineage")
    verification = payload.get("verification_result")
    eligibility = payload.get("rollback_recovery_eligibility")

    if not isinstance(authority, dict) or not authority:
        return False
    if not str(payload.get("runtime_evidence_id") or "").strip():
        return False
    if not isinstance(audit, dict) or not audit.get("evidence_id"):
        return False
    if not isinstance(lineage, dict):
        return False
    if not (
        lineage.get("transaction_id")
        or lineage.get("mutation_transaction_id")
        or lineage.get("repair_transaction_id")
    ):
        return False
    if not lineage.get("mutation_request_id"):
        return False
    if not isinstance(verification, dict) or verification.get("status") != "passed":
        return False
    if not isinstance(eligibility, dict):
        return False
    if eligibility.get("rollback_state") != "rollback_ready":
        return False
    if not eligibility.get("replay_session_id"):
        return False
    return eligibility.get("recovery_lineage_required") is True

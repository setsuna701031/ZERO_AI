from __future__ import annotations

from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH_FLOW_DOC = REPO_ROOT / "docs" / "patch_diff_apply_flow.md"
SELF_EDIT_GATE_TEST = REPO_ROOT / "tests" / "test_governed_self_edit_gate_contract.py"
MAINLINE_FREEZE_TEST = REPO_ROOT / "tests" / "test_runtime_mainline_freeze_contract.py"
TOPOLOGY_FREEZE_TEST = REPO_ROOT / "tests" / "test_runtime_topology_freeze_gate.py"


def test_patch_diff_apply_document_records_governed_flow_and_baselines() -> None:
    text = PATCH_FLOW_DOC.read_text(encoding="utf-8")

    for phrase in (
        "repo scan",
        "impacted file plan",
        "proposed diff",
        "approval/authority gate",
        "governed mutation request",
        "apply transaction",
        "verification command",
        "sealed evidence/audit",
        "rollback/recovery eligibility",
        "runtime owns execution authority",
        "scheduler remains compatibility and orchestration only",
        "`system_boot.py` remains bootstrap only",
    ):
        assert phrase in text

    assert SELF_EDIT_GATE_TEST.exists()
    assert MAINLINE_FREEZE_TEST.exists()
    assert TOPOLOGY_FREEZE_TEST.exists()


def test_canonical_patch_diff_success_shape_requires_governed_lineage() -> None:
    canonical = {
        "patch_diff_state": "succeeded",
        "plan_id": "patch-plan-1",
        "diff_id": "diff-1",
        "authority_metadata": {
            "runtime_identity": {"identity_type": "SYSTEM"},
            "authority_scope_id": "authority:patch-diff",
            "capability_scope_id": "capability:patch-diff",
        },
        "runtime_evidence_id": "runtime-evidence-1",
        "runtime_audit_metadata": {
            "evidence_id": "runtime-evidence-1",
            "audit_id": "audit:patch-diff",
            "mutation_transaction_id": "repair-tx-1",
            "mutation_request_id": "repair-request:repair-tx-1",
        },
        "repair_or_mutation_lineage": {
            "transaction_id": "repair-tx-1",
            "mutation_transaction_id": "repair-tx-1",
            "mutation_request_id": "repair-request:repair-tx-1",
            "replay_id": "replay:repair-tx-1",
            "source": "runtime_repair_transaction",
        },
        "verification_result": {
            "status": "passed",
            "command": "python -m pytest tests/test_patch_diff_apply_flow_contract.py",
        },
        "rollback_eligibility": {
            "rollback_state": "rollback_ready",
            "rollback_available": True,
        },
        "recovery_eligibility": {
            "governed_lineage_required": True,
            "replay_session_id": "replay:repair-tx-1",
        },
    }

    assert _is_canonical_patch_diff_success(canonical) is True


def test_raw_direct_or_unverified_patch_shapes_are_not_canonical_success() -> None:
    raw_file_write = {
        "patch_diff_state": "succeeded",
        "path": "core/runtime/example.py",
        "written": True,
    }
    direct_patch_apply = {
        "patch_diff_state": "succeeded",
        "plan_id": "patch-plan-1",
        "diff_id": "diff-1",
        "apply_result": {"applied": True},
        "verification_result": {"status": "passed"},
    }
    missing_verification = {
        "patch_diff_state": "succeeded",
        "plan_id": "patch-plan-1",
        "diff_id": "diff-1",
        "authority_metadata": {"authority_scope_id": "authority:patch-diff"},
        "runtime_evidence_id": "runtime-evidence-1",
        "runtime_audit_metadata": {"evidence_id": "runtime-evidence-1"},
        "repair_or_mutation_lineage": {
            "transaction_id": "repair-tx-1",
            "mutation_request_id": "repair-request:repair-tx-1",
        },
        "rollback_eligibility": {"rollback_state": "rollback_ready"},
        "recovery_eligibility": {"governed_lineage_required": True},
    }
    missing_rollback = {
        "patch_diff_state": "succeeded",
        "plan_id": "patch-plan-1",
        "diff_id": "diff-1",
        "authority_metadata": {"authority_scope_id": "authority:patch-diff"},
        "runtime_evidence_id": "runtime-evidence-1",
        "runtime_audit_metadata": {"evidence_id": "runtime-evidence-1"},
        "repair_or_mutation_lineage": {
            "transaction_id": "repair-tx-1",
            "mutation_request_id": "repair-request:repair-tx-1",
        },
        "verification_result": {"status": "passed"},
        "recovery_eligibility": {"governed_lineage_required": True},
    }

    for payload in (
        raw_file_write,
        direct_patch_apply,
        missing_verification,
        missing_rollback,
    ):
        assert _is_canonical_patch_diff_success(payload) is False


def _is_canonical_patch_diff_success(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("patch_diff_state") != "succeeded":
        return False
    if not str(payload.get("plan_id") or "").strip():
        return False
    if not str(payload.get("diff_id") or "").strip():
        return False
    if not isinstance(payload.get("authority_metadata"), dict) or not payload["authority_metadata"]:
        return False
    if not str(payload.get("runtime_evidence_id") or "").strip():
        return False

    audit = payload.get("runtime_audit_metadata")
    lineage = payload.get("repair_or_mutation_lineage")
    verification = payload.get("verification_result")
    rollback = payload.get("rollback_eligibility")
    recovery = payload.get("recovery_eligibility")

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
    if not isinstance(rollback, dict) or rollback.get("rollback_state") != "rollback_ready":
        return False
    if not isinstance(recovery, dict):
        return False
    return recovery.get("governed_lineage_required") is True

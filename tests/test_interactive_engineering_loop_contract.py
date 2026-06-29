from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest

pytestmark = [pytest.mark.contract]




REPO_ROOT = Path(__file__).resolve().parents[1]
LOOP_DOC = REPO_ROOT / "docs" / "interactive_engineering_loop.md"
SELF_EDIT_DOC = REPO_ROOT / "docs" / "governed_self_edit_upper_layer.md"
PATCH_FLOW_DOC = REPO_ROOT / "docs" / "patch_diff_apply_flow.md"


def test_interactive_engineering_loop_document_records_expected_flow() -> None:
    text = LOOP_DOC.read_text(encoding="utf-8")

    for phrase in (
        "user task",
        "repo scan",
        "impacted file analysis",
        "execution plan",
        "diff proposal",
        "approval/authority gate",
        "governed mutation/apply transaction",
        "verification commands",
        "retry/repair loop eligibility",
        "rollback/recovery eligibility",
        "execution summary/report",
        "Runtime Kernel Responsibilities",
        "Engineering Workflow Responsibilities",
        "Planner Responsibilities",
        "Mutation Responsibilities",
        "Approval And Authority Responsibilities",
    ):
        assert phrase in text

    assert SELF_EDIT_DOC.exists()
    assert PATCH_FLOW_DOC.exists()


def test_canonical_interactive_engineering_loop_shape_requires_governed_lineage() -> None:
    canonical = {
        "loop_state": "succeeded",
        "plan_id": "engineering-plan-1",
        "impacted_files": ["docs/interactive_engineering_loop.md"],
        "diff_proposal": {
            "diff_id": "diff-1",
            "status": "proposed",
            "files": ["docs/interactive_engineering_loop.md"],
        },
        "authority_approval": {
            "approval_id": "approval-1",
            "approved": True,
            "authority_scope_id": "authority:engineering-loop",
            "capability_scope_id": "capability:engineering-loop",
        },
        "governed_mutation_lineage": {
            "transaction_id": "repair-tx-1",
            "mutation_transaction_id": "repair-tx-1",
            "mutation_request_id": "repair-request:repair-tx-1",
            "source": "runtime_repair_transaction",
        },
        "runtime_evidence_id": "runtime-evidence-1",
        "runtime_audit_metadata": {
            "evidence_id": "runtime-evidence-1",
            "audit_id": "audit:engineering-loop",
        },
        "verification_result": {
            "status": "passed",
            "commands": ["python -m pytest tests/test_interactive_engineering_loop_contract.py"],
        },
        "rollback_eligibility": {
            "rollback_state": "rollback_ready",
            "rollback_available": True,
        },
        "recovery_eligibility": {
            "governed_lineage_required": True,
            "replay_session_id": "replay:repair-tx-1",
        },
        "execution_summary": {
            "summary_id": "summary-1",
            "status": "succeeded",
            "files_changed": ["docs/interactive_engineering_loop.md"],
        },
    }

    assert _is_canonical_interactive_engineering_loop_success(canonical) is True


def test_incomplete_or_bypassing_loop_shapes_are_not_canonical_success() -> None:
    raw_write_only = {
        "loop_state": "succeeded",
        "plan_id": "engineering-plan-1",
        "impacted_files": ["core/runtime/example.py"],
        "write_result": {"written": True},
    }
    missing_verification = {
        "loop_state": "succeeded",
        "plan_id": "engineering-plan-1",
        "impacted_files": ["docs/example.md"],
        "diff_proposal": {"diff_id": "diff-1"},
        "authority_approval": {"approval_id": "approval-1", "approved": True},
        "governed_mutation_lineage": {
            "transaction_id": "repair-tx-1",
            "mutation_request_id": "repair-request:repair-tx-1",
        },
        "runtime_evidence_id": "runtime-evidence-1",
        "runtime_audit_metadata": {"evidence_id": "runtime-evidence-1"},
        "rollback_eligibility": {"rollback_state": "rollback_ready"},
        "recovery_eligibility": {"governed_lineage_required": True},
        "execution_summary": {"summary_id": "summary-1"},
    }
    missing_approval_lineage = {
        "loop_state": "succeeded",
        "plan_id": "engineering-plan-1",
        "impacted_files": ["docs/example.md"],
        "diff_proposal": {"diff_id": "diff-1"},
        "governed_mutation_lineage": {
            "transaction_id": "repair-tx-1",
            "mutation_request_id": "repair-request:repair-tx-1",
        },
        "runtime_evidence_id": "runtime-evidence-1",
        "runtime_audit_metadata": {"evidence_id": "runtime-evidence-1"},
        "verification_result": {"status": "passed"},
        "rollback_eligibility": {"rollback_state": "rollback_ready"},
        "recovery_eligibility": {"governed_lineage_required": True},
        "execution_summary": {"summary_id": "summary-1"},
    }
    missing_runtime_evidence = {
        "loop_state": "succeeded",
        "plan_id": "engineering-plan-1",
        "impacted_files": ["docs/example.md"],
        "diff_proposal": {"diff_id": "diff-1"},
        "authority_approval": {"approval_id": "approval-1", "approved": True},
        "governed_mutation_lineage": {
            "transaction_id": "repair-tx-1",
            "mutation_request_id": "repair-request:repair-tx-1",
        },
        "runtime_audit_metadata": {"evidence_id": "runtime-evidence-1"},
        "verification_result": {"status": "passed"},
        "rollback_eligibility": {"rollback_state": "rollback_ready"},
        "recovery_eligibility": {"governed_lineage_required": True},
        "execution_summary": {"summary_id": "summary-1"},
    }
    direct_planner_owned_execution = {
        "loop_state": "succeeded",
        "plan_id": "engineering-plan-1",
        "impacted_files": ["docs/example.md"],
        "diff_proposal": {"diff_id": "diff-1"},
        "authority_approval": {"approval_id": "approval-1", "approved": True},
        "planner_execution": {"executed": True, "owner": "planner"},
        "runtime_evidence_id": "runtime-evidence-1",
        "runtime_audit_metadata": {"evidence_id": "runtime-evidence-1"},
        "verification_result": {"status": "passed"},
        "rollback_eligibility": {"rollback_state": "rollback_ready"},
        "recovery_eligibility": {"governed_lineage_required": True},
        "execution_summary": {"summary_id": "summary-1"},
    }

    for payload in (
        raw_write_only,
        missing_verification,
        missing_approval_lineage,
        missing_runtime_evidence,
        direct_planner_owned_execution,
    ):
        assert _is_canonical_interactive_engineering_loop_success(payload) is False


def _is_canonical_interactive_engineering_loop_success(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("loop_state") != "succeeded":
        return False
    if payload.get("planner_execution"):
        return False
    if not str(payload.get("plan_id") or "").strip():
        return False

    impacted_files = payload.get("impacted_files")
    diff_proposal = payload.get("diff_proposal")
    approval = payload.get("authority_approval")
    lineage = payload.get("governed_mutation_lineage")
    audit = payload.get("runtime_audit_metadata")
    verification = payload.get("verification_result")
    rollback = payload.get("rollback_eligibility")
    recovery = payload.get("recovery_eligibility")
    summary = payload.get("execution_summary")

    if not isinstance(impacted_files, list) or not impacted_files:
        return False
    if not isinstance(diff_proposal, dict) or not diff_proposal.get("diff_id"):
        return False
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        return False
    if not approval.get("approval_id"):
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
    if not str(payload.get("runtime_evidence_id") or "").strip():
        return False
    if not isinstance(audit, dict) or not audit.get("evidence_id"):
        return False
    if not isinstance(verification, dict) or verification.get("status") != "passed":
        return False
    if not isinstance(rollback, dict) or rollback.get("rollback_state") != "rollback_ready":
        return False
    if not isinstance(recovery, dict) or recovery.get("governed_lineage_required") is not True:
        return False
    if not isinstance(summary, dict) or not summary.get("summary_id"):
        return False
    return True

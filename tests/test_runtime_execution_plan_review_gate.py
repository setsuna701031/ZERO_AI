from __future__ import annotations

import copy

import pytest

from core.runtime.runtime_apply_execution_plan_builder import RuntimeApplyExecutionPlanBuilder
from core.runtime.runtime_execution_plan_review_gate import (
    RUNTIME_EXECUTION_PLAN_OPERATOR_REVIEW_CONTRACT, review_execution_plan,
)
from tests.test_runtime_apply_execution_plan_builder import NOW, lineage

EXPIRES = "2026-07-10T13:00:00+00:00"


def plan():
    p, a, d = lineage()
    return RuntimeApplyExecutionPlanBuilder(clock=lambda: NOW).build(
        proposal=p, approval_record=a, admission_record=d)


def security(value):
    keys = ("execution_started", "mutation_started", "mutation_allowed",
            "patch_generation_allowed", "patch_application_allowed",
            "autonomous_apply_allowed", "requires_controlled_executor",
            "requires_separate_execution_step", "requires_post_execution_validation",
            "requires_rollback_capability")
    return {key: value[key] for key in keys}


def review(value, decision="approved", **updates):
    result = {
        "contract": RUNTIME_EXECUTION_PLAN_OPERATOR_REVIEW_CONTRACT,
        "review_id": "review-one", "plan_id": value["plan_id"],
        "operator_id": "operator", "decision": decision,
        "reviewed_at": NOW, "expires_at": EXPIRES,
        "acknowledged_scope": copy.deepcopy(value["allowed_files"]),
        "acknowledged_constraints": copy.deepcopy(value["execution_constraints"]),
        "acknowledged_security_invariants": security(value),
        "acknowledged_evidence_requirements": copy.deepcopy(value["evidence_requirements"]),
        "notes": "reviewed",
    }
    result.update(updates); return result


def test_approved_and_rejected_are_valid_deterministic_and_never_execute():
    p = plan(); r = review(p); before = copy.deepcopy((p, r))
    first = review_execution_plan(p, r, now=NOW)
    second = review_execution_plan(p, r, now=NOW)
    rejected = review_execution_plan(p, review(p, "rejected"), now=NOW)
    assert first["review_status"] == "approved" and first["review_valid"] is True
    assert first["executor_admission_ready"] is True and first["execution_allowed"] is False
    assert first["result_id"] == second["result_id"] and (p, r) == before
    assert rejected["review_status"] == "rejected" and rejected["review_valid"] is True
    assert rejected["executor_admission_ready"] is False and rejected["execution_allowed"] is False


@pytest.mark.parametrize(("updates", "reason"), [
    ({"operator_id": ""}, "operator_id_required"),
    ({"review_id": ""}, "review_id_required"),
    ({"plan_id": "wrong"}, "plan_id_mismatch"),
    ({"decision": "yes"}, "invalid_decision"),
    ({"decision": True}, "invalid_decision"),
    ({"reviewed_at": "bad"}, "invalid_reviewed_at"),
    ({"expires_at": NOW}, "expiration_not_after_review"),
    ({"acknowledged_scope": ["other.txt"]}, "acknowledged_scope_mismatch"),
    ({"acknowledged_constraints": {}}, "acknowledged_constraints_mismatch"),
    ({"acknowledged_evidence_requirements": []}, "acknowledged_evidence_requirements_mismatch"),
    ({"auto_approve": True}, "unsafe_override:auto_approve"),
    ({"skip_validation": True}, "unsafe_override:skip_validation"),
    ({"rollback_disabled": True}, "unsafe_override:rollback_disabled"),
    ({"scope_expansion": True}, "unsafe_override:scope_expansion"),
    ({"mutation_allowed": True}, "unsafe_override:mutation_allowed"),
    ({"execution_allowed": True}, "unsafe_override:execution_allowed"),
])
def test_invalid_reviews_fail_closed(updates, reason):
    p = plan(); result = review_execution_plan(p, review(p, **updates), now=NOW)
    assert result["review_status"] == "invalid"
    assert reason in result["reasons"]
    assert result["executor_admission_ready"] is False and result["execution_allowed"] is False


@pytest.mark.parametrize(("change", "reason"), [
    (lambda p: p.update(proposal_id="wrong"), "proposal_id_chain_mismatch"),
    (lambda p: p.update(approval_id="wrong"), "approval_id_chain_mismatch"),
    (lambda p: p.update(admission_id="wrong"), "admission_id_chain_mismatch"),
    (lambda p: p.update(proposal_fingerprint="0" * 64), "proposal_fingerprint_mismatch"),
    (lambda p: p["execution_constraints"].pop("validation_required"), "invalid_execution_constraints"),
    (lambda p: p["execution_constraints"].update(validation_required=False), "invalid_execution_constraints"),
    (lambda p: p.update(mutation_allowed=True), "invalid_security_invariants"),
    (lambda p: p.update(execution_allowed=True), "unsafe_override:execution_allowed"),
    (lambda p: p.update(evidence_requirements=p["evidence_requirements"][:-1]), "invalid_evidence_requirements"),
])
def test_invalid_plans_fail_closed(change, reason):
    p = plan(); r = review(p); change(p)
    result = review_execution_plan(p, r, now=NOW)
    assert reason in result["reasons"] and result["executor_admission_ready"] is False


@pytest.mark.parametrize(("paths", "reason"), [
    (["workspace/a.txt", "new.txt"], "allowed_files_outside_admission_scope"),
    (["*.txt"], "invalid_allowed_files"), (["."], "invalid_allowed_files"),
    (["../x.txt"], "invalid_allowed_files"),
    (["workspace/a.txt", "workspace/a.txt"], "allowed_files_not_stable_deduplicated"),
])
def test_path_scope_rules(paths, reason):
    p = plan(); p["allowed_files"] = paths
    result = review_execution_plan(p, review(p), now=NOW)
    assert reason in result["reasons"]


def test_acknowledged_scope_canonical_duplicates_and_expiration():
    p = plan(); r = review(p)
    r["acknowledged_scope"] = p["allowed_files"] + p["allowed_files"]
    assert review_execution_plan(p, r, now=NOW)["review_status"] == "approved"
    expired = review_execution_plan(p, review(p), now=EXPIRES)
    assert "review_expired" in expired["reasons"]


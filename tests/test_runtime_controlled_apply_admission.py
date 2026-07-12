from __future__ import annotations

import copy

import pytest

from core.runtime.runtime_controlled_apply_admission import RuntimeControlledApplyAdmission
from core.runtime.runtime_operator_approval_gate import RuntimeOperatorApprovalGate

NOW = "2026-07-10T12:00:00+00:00"


def proposal(**updates):
    value = {"schema": "zero.runtime.change_proposal_engine.v1", "ok": True,
             "proposal_status": "proposal_created", "proposal_id": "p1",
             "requires_operator_approval": True, "mutation_allowed": False,
             "autonomous_apply_allowed": False, "patch_generation_allowed": False,
             "proposal": {"target_files": ["workspace/a.txt"],
                          "recommended_actions": ["review"],
                          "validation_requirements": ["test"],
                          "rollback_requirements": ["rollback"]}}
    value.update(updates); return value


def approval(value=None, **updates):
    value = value or proposal()
    result = RuntimeOperatorApprovalGate(clock=lambda: NOW).review(
        proposal=value, decision="approve", operator_id="operator")
    result.update(updates); return result


def gate(): return RuntimeControlledApplyAdmission(clock=lambda: NOW)


def test_admitted_is_deterministic_pure_and_never_executes():
    p = proposal(); a = approval(p); before = (copy.deepcopy(p), copy.deepcopy(a))
    first = gate().admit(proposal=p, approval_record=a, controlled=True)
    second = gate().admit(proposal=p, approval_record=a, controlled=True)
    assert first["admission_status"] == "admitted" and first["apply_admitted"] is True
    assert first["admission_id"] == second["admission_id"]
    assert (p, a) == before
    for key in ("execution_started", "mutation_started", "mutation_allowed",
                "patch_application_allowed", "repair_execution_allowed",
                "autonomous_apply_allowed", "decision_authority",
                "requested_changes_modified"):
        assert first[key] is False
    assert first["requires_controlled_executor"] is True
    assert first["requires_separate_apply_step"] is True
    assert first["audit_record"]["security_invariants"]["mutation_started"] is False


@pytest.mark.parametrize(("pupdate", "aupdate", "controlled", "status"), [
    ({}, {}, False, "denied_uncontrolled_mode"),
    ({"schema": "wrong"}, {}, True, "denied_invalid_proposal"),
    ({}, {"schema": "wrong"}, True, "denied_invalid_approval"),
    ({}, {"approval_status": "rejected"}, True, "denied_not_approved"),
    ({}, {"revoked": True}, True, "denied_revoked"),
    ({}, {"operator_id": ""}, True, "denied_missing_operator_approval"),
    ({"mutation_allowed": True}, {}, True, "denied_safety_invariant_violation"),
    ({}, {"execution_authority_granted": True}, True, "denied_safety_invariant_violation"),
])
def test_denials(pupdate, aupdate, controlled, status):
    p = proposal(**pupdate); a = approval(proposal())
    a.update(aupdate)
    result = gate().admit(proposal=p, approval_record=a, controlled=controlled)
    assert result["admission_status"] == status and result["apply_admitted"] is False


def test_fingerprint_scope_and_expiration_denials():
    p = proposal(); a = approval(p)
    changed = copy.deepcopy(p); changed["proposal"]["recommended_actions"].append("extra")
    assert gate().admit(proposal=changed, approval_record=a, controlled=True)["admission_status"] == "denied_proposal_fingerprint_mismatch"
    bad_scope = copy.deepcopy(a); bad_scope["scope_fingerprint"] = "bad"
    assert gate().admit(proposal=p, approval_record=bad_scope, controlled=True)["admission_status"] == "denied_scope_fingerprint_mismatch"
    expired = approval(p, expires_at=NOW)
    assert gate().admit(proposal=p, approval_record=expired, controlled=True)["admission_status"] == "denied_expired"


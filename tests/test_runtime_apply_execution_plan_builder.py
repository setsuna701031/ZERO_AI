from __future__ import annotations

import copy
from hashlib import sha256
import json

import pytest

from core.runtime.runtime_apply_execution_plan_builder import RuntimeApplyExecutionPlanBuilder
from core.runtime.runtime_controlled_apply_admission import RuntimeControlledApplyAdmission
from core.runtime.runtime_operator_approval_gate import RuntimeOperatorApprovalGate

NOW = "2026-07-10T12:00:00+00:00"


def proposal(**updates):
    result = {
        "schema": "zero.runtime.change_proposal_engine.v1", "proposal_id": "p-one",
        "proposal_status": "proposal_created", "requires_operator_approval": True,
        "mutation_allowed": False, "patch_generation_allowed": False,
        "autonomous_apply_allowed": False,
        "proposal": {
            "target_files": ["workspace/a.txt", "workspace/a.txt"],
            "recommended_actions": ["review_target_file"],
            "validation_requirements": ["run_focused_validation",
                "confirm_expected_file_state", "confirm_no_unapproved_paths_changed"],
            "rollback_requirements": [{"rollback_plan_required": True},
                {"rollback_evidence_required": True},
                "snapshot_target_files_before_change"],
        },
    }
    result.update(updates); return result


def lineage(p=None, *, expires_at=None):
    p = p or proposal()
    a = RuntimeOperatorApprovalGate(clock=lambda: NOW).review(
        proposal=p, decision="approve", operator_id="operator", expires_at=expires_at)
    d = RuntimeControlledApplyAdmission(clock=lambda: NOW).admit(
        proposal=p, approval_record=a, controlled=True)
    return p, a, d


def builder(): return RuntimeApplyExecutionPlanBuilder(clock=lambda: NOW)


def fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()


def test_ready_is_deterministic_pure_structured_and_non_executable():
    p, a, d = lineage(); before = copy.deepcopy((p, a, d))
    first = builder().build(proposal=p, approval_record=a, admission_record=d)
    second = builder().build(proposal=p, approval_record=a, admission_record=d)
    assert first["plan_status"] == "ready" and first["plan_ready"] is True
    assert first["plan_id"] == second["plan_id"] and (p, a, d) == before
    assert first["allowed_files"] == ["workspace/a.txt"]
    assert all(step["execution_allowed"] is False for step in first["validation_plan"])
    assert all("command" not in step for step in first["validation_plan"])
    assert first["rollback_plan"]["execution_allowed"] is False
    for key in ("execution_started", "mutation_started", "mutation_allowed",
                "patch_generation_allowed", "patch_application_allowed",
                "autonomous_apply_allowed", "decision_authority",
                "requested_changes_modified"):
        assert first[key] is False
    assert first["audit_record"]["validation_step_count"] == 3
    assert len(first["evidence_requirements"]) == 7


@pytest.mark.parametrize(("which", "updates", "status"), [
    ("proposal", {"schema": "wrong"}, "denied_invalid_proposal"),
    ("approval", {"schema": "wrong"}, "denied_invalid_approval"),
    ("admission", {"schema": "wrong"}, "denied_invalid_admission"),
    ("approval", {"approval_status": "rejected"}, "denied_invalid_approval"),
    ("admission", {"admission_status": "denied", "apply_admitted": False}, "denied_not_admitted"),
    ("admission", {"controlled": False}, "denied_uncontrolled"),
    ("approval", {"revoked": True}, "denied_revoked"),
    ("approval", {"expired": True}, "denied_expired"),
    ("proposal", {"mutation_allowed": True}, "denied_safety_invariant_violation"),
])
def test_primary_denials(which, updates, status):
    p, a, d = lineage(); records = {"proposal": p, "approval": a, "admission": d}
    records[which].update(updates)
    result = builder().build(proposal=p, approval_record=a, admission_record=d)
    assert result["plan_status"] == status and result["plan_ready"] is False


def test_cross_record_fingerprint_scope_and_expiration_denials():
    p, a, d = lineage()
    changed = copy.deepcopy(a); changed["proposal_id"] = "other"
    assert builder().build(proposal=p, approval_record=changed, admission_record=d)["plan_status"] == "denied_proposal_mismatch"
    changed = copy.deepcopy(d); changed["approval_id"] = "other"
    assert builder().build(proposal=p, approval_record=a, admission_record=changed)["plan_status"] == "denied_approval_mismatch"
    changed = copy.deepcopy(d); changed["proposal_fingerprint"] = "bad"
    assert builder().build(proposal=p, approval_record=a, admission_record=changed)["plan_status"] == "denied_fingerprint_mismatch"
    changed = copy.deepcopy(d); changed["scope"]["target_files"] = []
    assert builder().build(proposal=p, approval_record=a, admission_record=changed)["plan_status"] == "denied_scope_mismatch"
    p2, a2, d2 = lineage(expires_at="2026-07-10T13:00:00+00:00")
    result = builder().build(proposal=p2, approval_record=a2, admission_record=d2,
                             now="2026-07-10T13:00:00+00:00")
    assert result["plan_status"] == "denied_expired"


@pytest.mark.parametrize("path", ["C:/absolute.txt", "../escape.txt"])
def test_unsafe_proposal_paths_are_denied(path):
    p = proposal(); p["proposal"]["target_files"] = [path]
    _, a, d = lineage()
    assert builder().build(proposal=p, approval_record=a, admission_record=d)["plan_status"] == "denied_invalid_proposal"


def test_missing_validation_and_rollback_are_denied():
    p, a, d = lineage()
    missing = copy.deepcopy(d); missing["scope"]["validation_requirements"] = []
    missing["scope_fingerprint"] = fingerprint(missing["scope"])
    matching = copy.deepcopy(a); matching["approved_scope"] = copy.deepcopy(missing["scope"])
    matching["scope_fingerprint"] = missing["scope_fingerprint"]
    missing["approval_scope_fingerprint"] = missing["scope_fingerprint"]
    assert builder().build(proposal=p, approval_record=matching, admission_record=missing)["plan_status"] == "denied_missing_validation_plan"
    missing = copy.deepcopy(d); missing["scope"]["rollback_requirements"] = []
    missing["scope_fingerprint"] = fingerprint(missing["scope"])
    matching = copy.deepcopy(a); matching["approved_scope"] = copy.deepcopy(missing["scope"])
    matching["scope_fingerprint"] = missing["scope_fingerprint"]
    missing["approval_scope_fingerprint"] = missing["scope_fingerprint"]
    assert builder().build(proposal=p, approval_record=matching, admission_record=missing)["plan_status"] == "denied_missing_rollback_plan"


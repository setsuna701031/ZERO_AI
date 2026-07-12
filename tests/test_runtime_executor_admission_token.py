from __future__ import annotations

import copy

import pytest

from core.runtime.runtime_executor_admission_token import (
    RUNTIME_OPERATOR_EXECUTION_REQUEST_CONTRACT, issue_executor_admission_token,
)
from core.runtime.runtime_execution_plan_review_gate import review_execution_plan
from tests.test_runtime_execution_plan_review_gate import NOW, plan, review


def inputs(tmp_path):
    p = plan(); r = review_execution_plan(p, review(p), now=NOW)
    request = {"contract": RUNTIME_OPERATOR_EXECUTION_REQUEST_CONTRACT,
        "request_id": "request-one", "review_result_id": r["result_id"],
        "plan_id": p["plan_id"], "operator_id": r["operator_id"],
        "requested_mode": "controlled_dry_run", "requested_at": NOW,
        "expires_at": "2026-07-10T12:30:00+00:00",
        "acknowledged_scope": copy.deepcopy(p["allowed_files"]),
        "acknowledged_dry_run": True, "acknowledged_no_file_mutation": True}
    return p, r, request


def test_token_is_deterministic_bound_and_non_mutating(tmp_path):
    p, r, q = inputs(tmp_path); before = copy.deepcopy((p, r, q))
    first = issue_executor_admission_token(p, r, q, target_root=tmp_path, now=NOW)
    second = issue_executor_admission_token(p, r, q, target_root=tmp_path, now=NOW)
    assert first["token_status"] == "issued" and first["token_id"] == second["token_id"]
    assert first["execution_entry_allowed"] is True and first["dry_run_allowed"] is True
    assert (p, r, q) == before
    for key in ("execution_allowed", "file_mutation_allowed", "patch_application_allowed",
                "commit_allowed", "rollback_execution_allowed", "active_execution_ready"):
        assert first[key] is False


@pytest.mark.parametrize(("target", "updates", "reason"), [
    ("review", {"review_status": "rejected"}, "review_not_approved"),
    ("review", {"review_valid": False}, "review_not_approved"),
    ("review", {"executor_admission_ready": False}, "review_not_executor_ready"),
    ("review", {"execution_allowed": True}, "unsafe_review_execution_authority"),
    ("request", {"operator_id": ""}, "operator_id_required"),
    ("request", {"requested_mode": "active"}, "invalid_requested_mode"),
    ("request", {"expires_at": NOW}, "operator_request_expired"),
    ("request", {"plan_id": "wrong"}, "plan_id_mismatch"),
    ("request", {"review_result_id": "wrong"}, "review_result_id_mismatch"),
    ("request", {"acknowledged_scope": []}, "acknowledged_scope_mismatch"),
])
def test_token_denials(tmp_path, target, updates, reason):
    p, r, q = inputs(tmp_path); {"plan": p, "review": r, "request": q}[target].update(updates)
    token = issue_executor_admission_token(p, r, q, target_root=tmp_path, now=NOW)
    assert token["token_status"] == "denied" and reason in token["reasons"]
    assert token["execution_entry_allowed"] is False and token["dry_run_allowed"] is False


def test_token_binding_changes_across_plan_review_request_and_root(tmp_path):
    p, r, q = inputs(tmp_path)
    base = issue_executor_admission_token(p, r, q, target_root=tmp_path, now=NOW)["token_id"]
    variants = []
    p2 = copy.deepcopy(p); p2["plan_id"] = "other"; q2 = copy.deepcopy(q); q2["plan_id"] = "other"
    variants.append(issue_executor_admission_token(p2, r, q2, target_root=tmp_path, now=NOW)["token_id"])
    r2 = copy.deepcopy(r); r2["result_id"] = "other"; q2 = copy.deepcopy(q); q2["review_result_id"] = "other"
    variants.append(issue_executor_admission_token(p, r2, q2, target_root=tmp_path, now=NOW)["token_id"])
    q2 = copy.deepcopy(q); q2["request_id"] = "other"
    variants.append(issue_executor_admission_token(p, r, q2, target_root=tmp_path, now=NOW)["token_id"])
    other = tmp_path / "other"; other.mkdir()
    variants.append(issue_executor_admission_token(p, r, q, target_root=other, now=NOW)["token_id"])
    assert all(value != base for value in variants)


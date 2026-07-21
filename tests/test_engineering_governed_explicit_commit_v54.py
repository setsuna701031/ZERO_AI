from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core.engineering.engineering_governed_explicit_commit import *
from core.engineering.engineering_multifile_coding_workflow import canon


def art(schema: str, name: str, **values):
    return canon({"schema": schema, **values}, f"{name}_fingerprint", f"{name}_id", f"engineering-{name}-")


def git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)


def prepared(tmp_path: Path):
    root = tmp_path / "repo"; root.mkdir()
    git(root, "init", "-b", "main"); git(root, "config", "user.name", "ZERO Test"); git(root, "config", "user.email", "zero@example.invalid")
    (root / "value.txt").write_text("one\n", encoding="utf-8", newline="")
    git(root, "add", "--", "value.txt"); git(root, "commit", "-m", "initial")
    head = inspect_git_workspace(root)["head"]
    (root / "value.txt").write_text("two\n", encoding="utf-8", newline="")
    review = art("review", "review", decision="completed")
    result = art("result", "result", mutation_status="applied", changed_paths=["value.txt"])
    verification = art("verification", "apply-verification", verification_status="passed", completion_eligible=True)
    package = art("package", "package", ordered_paths=["value.txt"], ordered_operations=[{"operation_id": "op-1"}],
                  verification_plan={"targets": ["tests/test_value.py"]}, pre_apply_head=head, session_id="s54")
    usage = art("usage", "usage", authorization_usage="consumed")
    preparation = build_commit_preparation_intake(review, result, verification, package, usage, workspace_root=root)
    assert preparation["preparation_status"] == "prepared", preparation["reason_codes"]
    candidate = build_commit_candidate(preparation, commit_message="feat: governed fixture", workspace_root=root)
    diff = verify_commit_diff(candidate, preparation, workspace_root=root)
    admission = admit_commit(preparation, candidate, diff, review, usage)
    raw = {"human_actor": "alice", "decision": "confirmed", "confirmed_commit_message": "feat: governed fixture",
           "confirmed_paths": ["value.txt"], "confirmed_diff_fingerprint": candidate["diff_fingerprint"],
           "confirmed_head": candidate["pre_commit_head"], "risk_acknowledgements": ["local commit only"]}
    request = build_explicit_commit_request(candidate, admission, raw)
    return root, review, result, verification, package, usage, preparation, candidate, diff, admission, request


def test_preparation_requires_completed_applied_verified_consumed_and_exact_paths(tmp_path):
    p = prepared(tmp_path)
    assert p[6]["schema"] == PREPARATION_SCHEMA and p[6]["preparation_status"] == "prepared"
    blocked = build_commit_preparation_intake({**p[1], "decision": "rejected"}, p[2], p[3], p[4], p[5], workspace_root=p[0])
    assert blocked["preparation_status"] == "blocked" and "completion_review_not_completed" in blocked["reason_codes"]


def test_candidate_and_diff_have_no_commit_authority(tmp_path):
    p = prepared(tmp_path)
    assert p[7]["schema"] == CANDIDATE_SCHEMA and not p[7]["authority"]["may_commit"]
    assert p[8]["verification_status"] == "verified" and not p[8]["staged_paths"]


def test_diff_fails_closed_for_untracked_staged_and_drift(tmp_path):
    p = prepared(tmp_path); (p[0] / "extra.txt").write_text("x\n", encoding="utf-8")
    assert "untracked_file_present" in verify_commit_diff(p[7], p[6], workspace_root=p[0])["reason_codes"]
    (p[0] / "extra.txt").unlink(); git(p[0], "add", "--", "value.txt")
    assert "staged_unstaged_mismatch" in verify_commit_diff(p[7], p[6], workspace_root=p[0])["reason_codes"]


def test_explicit_request_exact_binding_and_replay_protection(tmp_path):
    p = prepared(tmp_path)
    with pytest.raises(GovernedCommitError, match="missing_human_actor"):
        build_explicit_commit_request(p[7], p[9], {})
    bad = {**p[10], "confirmed_commit_message": "substituted"}
    with pytest.raises(GovernedCommitError, match="commit_message_substitution"):
        execute_governed_commit(bad, p[9], p[7], workspace_root=p[0])


def test_governed_commit_fixture_records_and_verifies_without_push(tmp_path):
    p = prepared(tmp_path)
    request, admission, evidence = execute_governed_commit(p[10], p[9], p[7], workspace_root=p[0])
    assert evidence["commit_status"] == "committed" and request["usage_status"] == "consumed" and admission["replay_status"] == "used"
    verification = verify_commit(evidence, request, workspace_root=p[0])
    assert verification["verification_status"] == "verified"
    assert verification["next_governed_action"] == "awaiting_explicit_push_review"
    assert verification["push_performed"] is False and inspect_git_workspace(p[0])["working_tree_clean"]
    with pytest.raises(GovernedCommitError, match="commit_admission_replay"):
        execute_governed_commit(request, admission, p[7], workspace_root=p[0])


def test_inspect_resume_store_contract_and_cli_surface(tmp_path):
    p = prepared(tmp_path); bundle = {STORE_FILES["candidate"]: p[7]}
    state = resume_commit_state(bundle)
    assert state["decision"] == "validate-commit-candidate" and not any(state[f"will_{x}"] for x in ("commit", "push", "create_pr", "merge", "tag", "release", "retry", "complete"))
    cp = subprocess.run([sys.executable, "-m", "cli.zero_engineering_work", "--help"], cwd=Path(__file__).parents[1], text=True, capture_output=True)
    assert cp.returncode == 0
    for command in ("prepare-commit", "commit-candidate", "validate-commit-candidate", "admit-commit", "confirm-commit", "reject-commit", "execute-commit", "commit-evidence", "verify-commit"):
        assert command in cp.stdout
    for forbidden in ("auto-commit", "commit-latest", "force-commit", "push", "create-pr", "merge", "tag", "release"):
        assert forbidden not in cp.stdout

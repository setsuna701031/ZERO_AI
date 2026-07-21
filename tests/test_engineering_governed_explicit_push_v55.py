from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core.engineering.engineering_governed_explicit_push import *
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_runtime_session_store import read_session_artifact, write_session_artifact


def git(root: Path, *args: str, check: bool = True):
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=check)


def art(schema: str, name: str, **values):
    return canon({"schema": schema, **values}, f"{name}_fingerprint", f"{name}_id", f"engineering-{name}-")


def fixture(tmp_path: Path):
    remote = tmp_path / "remote.git"; git(tmp_path, "init", "--bare", str(remote))
    root = tmp_path / "repo"; root.mkdir(); git(root, "init", "-b", "main")
    git(root, "config", "user.name", "ZERO Test"); git(root, "config", "user.email", "zero@example.invalid")
    (root / "value.txt").write_text("one\n", encoding="utf-8"); git(root, "add", "--", "value.txt"); git(root, "commit", "-m", "base")
    git(root, "remote", "add", "origin", str(remote)); parent = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "push", "origin", f"{parent}:refs/heads/main")
    (root / "value.txt").write_text("two\n", encoding="utf-8"); git(root, "add", "--", "value.txt"); git(root, "commit", "-m", "change")
    target = git(root, "rev-parse", "HEAD").stdout.strip()
    evidence = art("zero.engineering.commit_evidence.v1", "commit-evidence", commit_status="committed", commit_sha=target,
                   pre_commit_head=parent, post_commit_head=target)
    verification = art("zero.engineering.commit_verification.v1", "commit-verification", verification_status="verified",
                       next_governed_action="awaiting_explicit_push_review", commit_sha=target, commit_parent=parent)
    prep = build_push_preparation(verification, evidence, remote="origin", branch="main", workspace_root=root)
    before = verify_remote(prep, workspace_root=root)
    review = review_push(prep, before, {"human_actor": "reviewer", "decision": "approved", "risk_acknowledgements": ["remote mutation"]})
    authorization = authorize_push(prep, before, review, {"human_actor": "authorizer", "decision": "authorized",
        "confirmed_push_fingerprint": prep["push_fingerprint"], "confirmed_local_head": target, "confirmed_remote_head": parent})
    return root, remote, evidence, verification, prep, before, review, authorization


def test_normal_exact_sha_push_evidence_verification_and_closure(tmp_path):
    p = fixture(tmp_path)
    used, execution = execute_push(p[4], p[5], p[6], p[7], p[3], p[2], observed_at="2026-07-21T00:00:00Z", workspace_root=p[0])
    assert execution["execution_status"] == "pushed"
    assert execution["refspec"] == f"{p[4]['commit_sha']}:refs/heads/main" and "HEAD" not in execution["refspec"]
    evidence = build_push_evidence(p[4], execution, observed_at="2026-07-21T00:00:01Z", workspace_root=p[0])
    after = verify_remote(p[4], workspace_root=p[0], phase="after_push", expected_commit=p[4]["commit_sha"])
    closure = close_push(p[4], used, execution, evidence, after, closed_at="2026-07-21T00:00:02Z")
    assert evidence["remote_commit"] == p[4]["commit_sha"] and after["verification_status"] == "verified"
    assert closure["closure_status"] == "closed" and closure["next_governed_action"] == "push_complete"


def test_push_request_preserves_complete_commit_and_remote_fingerprint(tmp_path):
    p = fixture(tmp_path); prep = p[4]
    for key in ("repository_id", "remote_name", "remote_url", "branch", "commit_sha", "parent_sha", "tree_sha", "commit_fingerprint", "push_fingerprint"):
        assert prep[key]
    assert p[6]["reviewed_push_fingerprint"] == prep["push_fingerprint"]
    assert p[7]["confirmed_push_fingerprint"] == prep["push_fingerprint"]


def test_rejected_review_and_missing_authorization_block(tmp_path):
    p = fixture(tmp_path)
    rejected = review_push(p[4], p[5], {"human_actor": "r", "decision": "rejected"})
    denied = authorize_push(p[4], p[5], rejected, {"human_actor": "a", "decision": "authorized",
        "confirmed_push_fingerprint": p[4]["push_fingerprint"], "confirmed_local_head": p[4]["commit_sha"], "confirmed_remote_head": p[5]["remote_head"]})
    assert not denied["authorized"]
    with pytest.raises(GovernedPushError, match="push_not_authorized|push_review_not_approved"):
        execute_push(p[4], p[5], rejected, denied, p[3], p[2], observed_at="t", workspace_root=p[0])


def test_remote_freeze_blocks_change_after_review(tmp_path):
    p = fixture(tmp_path); git(p[0], "push", "origin", f"{p[4]['commit_sha']}:refs/heads/main")
    with pytest.raises(GovernedPushError, match="remote_changed_after_review"):
        execute_push(p[4], p[5], p[6], p[7], p[3], p[2], observed_at="t", workspace_root=p[0])


def test_local_freeze_blocks_head_change_after_review(tmp_path):
    p = fixture(tmp_path); (p[0] / "later.txt").write_text("later\n", encoding="utf-8"); git(p[0], "add", "--", "later.txt"); git(p[0], "commit", "-m", "later")
    with pytest.raises(GovernedPushError, match="local_branch_changed"):
        execute_push(p[4], p[5], p[6], p[7], p[3], p[2], observed_at="t", workspace_root=p[0])


def test_commit_verification_is_revalidated_immediately_before_push(tmp_path):
    p = fixture(tmp_path); changed = {**p[3], "verification_status": "failed"}
    with pytest.raises(GovernedPushError, match="commit_verification_changed|commit_verification_not_valid"):
        execute_push(p[4], p[5], p[6], p[7], changed, p[2], observed_at="t", workspace_root=p[0])


@pytest.mark.parametrize(("remote", "commit", "branch", "extra", "reason"), [
    ("origin", "a" * 40, "main", ["--force"], "force_push_forbidden"),
    ("origin", "a" * 40, ":main", [], "branch_deletion_forbidden"),
    ("origin", "a" * 40, "main", ["--all"], "wildcard_push_forbidden"),
    ("origin", "a" * 40, "refs/tags/v1", [], "tag_push_forbidden"),
    ("origin", "HEAD", "main", [], "invalid_target_commit"),
])
def test_forbidden_push_shapes(remote, commit, branch, extra, reason):
    assert reason in validate_push_operation(remote, commit, branch, extra_args=extra)["reason_codes"]


def test_multiple_commits_fail_closed_and_fast_forward_is_verified(tmp_path):
    p = fixture(tmp_path); assert p[5]["fast_forward_eligible"]
    (p[0] / "third.txt").write_text("three\n", encoding="utf-8"); git(p[0], "add", "--", "third.txt"); git(p[0], "commit", "-m", "third")
    target = git(p[0], "rev-parse", "HEAD").stdout.strip(); parent = git(p[0], "rev-parse", f"{target}^").stdout.strip()
    evidence = art("e", "e2", commit_status="committed", commit_sha=target, pre_commit_head=parent)
    verification = art("v", "v2", verification_status="verified", next_governed_action="awaiting_explicit_push_review", commit_sha=target, commit_parent=parent)
    prep = build_push_preparation(verification, evidence, remote="origin", branch="main", workspace_root=p[0])
    check = verify_remote(prep, workspace_root=p[0])
    assert check["verification_status"] == "failed" and "multiple_commits_forbidden" in check["reason_codes"]


def test_inspect_resume_never_acts_implicitly(tmp_path):
    p = fixture(tmp_path); state = resume_push_state({STORE_FILES["remote_before"]: p[5]})
    assert state["decision"] == "review-push"
    assert not any(state[f"will_{x}"] for x in ("push", "retry", "pull", "merge", "rebase", "create_pr", "tag", "release"))


def test_session_store_and_dedicated_cli_contract(tmp_path):
    for path in STORE_FILES.values():
        write_session_artifact(tmp_path, "s55", path, {"schema": "test"})
        assert read_session_artifact(tmp_path, "s55", path) == {"schema": "test"}
    cp = subprocess.run([sys.executable, "-m", "cli.zero_engineering_runtime_push", "--help"],
                        cwd=Path(__file__).parents[1], text=True, capture_output=True)
    assert cp.returncode == 0
    for command in ("prepare-push", "verify-remote-before", "review-push", "authorize-push", "execute-push",
                    "push-evidence", "verify-remote-after", "close-push", "inspect", "resume"):
        assert command in cp.stdout
    for forbidden in ("force-push", "create-pr", "merge", "pull", "rebase", "create-tag", "release", "retry"):
        assert forbidden not in cp.stdout

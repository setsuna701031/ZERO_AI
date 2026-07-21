from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.engineering.engineering_governed_explicit_commit import NO_AUTHORITY, inspect_git_workspace
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_practical_task_runner import _ref

PREPARATION_SCHEMA = "zero.engineering.push_preparation.v1"
VERIFIED_COMMIT_CLOSURE_SCHEMA = "zero.engineering.verified_commit_closure.v1"
REMOTE_VERIFICATION_SCHEMA = "zero.engineering.remote_verification.v1"
REVIEW_SCHEMA = "zero.engineering.human_push_review.v1"
AUTHORIZATION_SCHEMA = "zero.engineering.explicit_push_authorization.v1"
EXECUTION_SCHEMA = "zero.engineering.push_execution.v1"
EVIDENCE_SCHEMA = "zero.engineering.push_evidence.v1"
CLOSURE_SCHEMA = "zero.engineering.push_closure.v1"
STORE_FILES = {
    "verified_commit_closure": "push/verified-commit-closure.json",
    "preparation": "push/preparation.json",
    "remote_before": "push/remote-verification-before.json",
    "review": "push/review.json",
    "authorization": "push/authorization.json",
    "execution": "push/execution.json",
    "evidence": "push/evidence.json",
    "remote_after": "push/remote-verification-after.json",
    "closure": "push/closure.json",
}
PUSH_AUTHORITY = {**NO_AUTHORITY, "may_push": True}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REMOTE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
BRANCH_RE = re.compile(r"^(?!-)(?!.*(?:\.\.|@\{|//|\\|\s|[~^:?*\[]))(?!.*(?:/|\.)$)[A-Za-z0-9._/-]{1,200}$")


class GovernedPushError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(["git", *args], cwd=root, text=True, encoding="utf-8", errors="replace",
                        capture_output=True, shell=False)
    if check and cp.returncode:
        raise GovernedPushError("git_command_failed")
    return cp


def _validate_target(remote: str, commit: str, branch: str, extra_args: Sequence[str] = ()) -> list[str]:
    errors = []
    tokens = [remote, commit, branch, *extra_args]
    lowered = [str(x).lower() for x in tokens]
    if not REMOTE_RE.fullmatch(remote or ""): errors.append("invalid_remote")
    if not SHA_RE.fullmatch(commit or ""): errors.append("invalid_target_commit")
    if (not BRANCH_RE.fullmatch(branch or "") or branch.startswith("refs/tags/") or branch.startswith(".")
            or "/." in branch or branch.endswith(".lock")): errors.append("invalid_branch")
    if extra_args: errors.append("additional_push_arguments_forbidden")
    if any(x in {"--force", "-f", "--force-with-lease"} or x.startswith("--force-with-lease=") for x in lowered): errors.append("force_push_forbidden")
    if any(x in {"--all", "--mirror"} for x in lowered) or any("*" in x for x in tokens): errors.append("wildcard_push_forbidden")
    if any(x.startswith("refs/tags/") or x == "tag" for x in lowered): errors.append("tag_push_forbidden")
    if any(str(x).startswith(":") or str(x).endswith(":") for x in tokens): errors.append("branch_deletion_forbidden")
    return sorted(set(errors))


def validate_push_operation(remote: str, commit: str, branch: str, *, extra_args: Sequence[str] = ()) -> dict[str, Any]:
    errors = _validate_target(remote, commit, branch, extra_args)
    return {"valid": not errors, "reason_codes": errors,
            "argv": ["git", "push", remote, f"{commit}:refs/heads/{branch}"] if not errors else None}


def _remote_url(root: Path, remote: str) -> str:
    value = _git(root, "remote", "get-url", "--push", remote).stdout.strip()
    if not value or re.search(r"(?i)https?://[^/@]+@", value) or "?" in value or "#" in value or "\n" in value or "\r" in value:
        raise GovernedPushError("unsafe_remote_url")
    return value


def _remote_head(root: Path, remote: str, branch: str) -> tuple[bool, str | None]:
    cp = _git(root, "ls-remote", "--heads", remote, f"refs/heads/{branch}", check=False)
    if cp.returncode:
        raise GovernedPushError("remote_inspection_failed")
    rows = [line.split() for line in cp.stdout.splitlines() if line.strip()]
    if len(rows) > 1: raise GovernedPushError("ambiguous_remote_branch")
    return (bool(rows), rows[0][0] if rows else None)


def _verified_closure_integrity_valid(closure: Mapping[str, Any]) -> bool:
    fingerprint_key = "verified_commit_closure_fingerprint"; identity_key = "verified_commit_closure_id"
    body = {key: value for key, value in closure.items() if key not in {fingerprint_key, identity_key}}
    rebuilt = canon(body, fingerprint_key, identity_key, "engineering-verified-commit-closure-")
    return rebuilt.get(fingerprint_key) == closure.get(fingerprint_key) and rebuilt.get(identity_key) == closure.get(identity_key)


def close_verified_commit(commit_verification: Mapping[str, Any], commit_evidence: Mapping[str, Any], *, workspace_root: str | Path = ".") -> dict[str, Any]:
    errors = []
    if commit_verification.get("schema") != "zero.engineering.commit_verification.v1": errors.append("invalid_commit_verification_schema")
    if commit_verification.get("verification_status") != "verified": errors.append("commit_verification_not_verified")
    if commit_evidence.get("schema") != "zero.engineering.commit_evidence.v1": errors.append("invalid_commit_evidence_schema")
    if commit_evidence.get("commit_status") != "committed": errors.append("commit_evidence_not_complete")
    if commit_verification.get("commit_sha") != commit_evidence.get("commit_sha"): errors.append("verified_commit_mismatch")
    commit_sha = str(commit_verification.get("commit_sha") or "")
    parent_sha = str(commit_verification.get("commit_parent") or "")
    tree_sha = ""
    if SHA_RE.fullmatch(commit_sha):
        root = Path(workspace_root).resolve()
        actual_parent = _git(root, "rev-parse", f"{commit_sha}^").stdout.strip()
        tree_sha = _git(root, "show", "-s", "--format=%T", commit_sha).stdout.strip()
        if actual_parent != parent_sha or commit_evidence.get("pre_commit_head") != parent_sha: errors.append("verified_commit_parent_mismatch")
    else: errors.append("invalid_verified_commit_sha")
    body = {"schema": VERIFIED_COMMIT_CLOSURE_SCHEMA,
            "commit_verification_reference": _ref(commit_verification), "commit_evidence_reference": _ref(commit_evidence),
            "commit_sha": commit_sha, "parent_sha": parent_sha, "tree_sha": tree_sha,
            "commit_verification_status": commit_verification.get("verification_status"),
            "commit_evidence_status": "complete" if commit_evidence.get("commit_status") == "committed" else "incomplete",
            "status": "verified" if not errors else "blocked", "sealed": not errors,
            "reason_codes": sorted(set(errors)), "authority": NO_AUTHORITY}
    return canon(body, "verified_commit_closure_fingerprint", "verified_commit_closure_id", "engineering-verified-commit-closure-")


def build_push_preparation(verified_commit_closure: Mapping[str, Any], *,
                           remote: str, branch: str, workspace_root: str | Path = ".") -> dict[str, Any]:
    root = Path(workspace_root).resolve(); snap = inspect_git_workspace(root)
    target = str(verified_commit_closure.get("commit_sha") or ""); parent = str(verified_commit_closure.get("parent_sha") or "")
    errors = _validate_target(remote, target, branch)
    if verified_commit_closure.get("schema") != VERIFIED_COMMIT_CLOSURE_SCHEMA or verified_commit_closure.get("status") != "verified" or verified_commit_closure.get("sealed") is not True: errors.append("verified_commit_closure_not_verified")
    if not _verified_closure_integrity_valid(verified_commit_closure): errors.append("verified_commit_closure_integrity_invalid")
    if verified_commit_closure.get("commit_evidence_status") != "complete": errors.append("commit_evidence_not_complete")
    if target != snap["head"]: errors.append("local_head_mismatch")
    if not snap["working_tree_clean"]: errors.append("working_tree_not_clean")
    if branch != snap["branch"]: errors.append("branch_mismatch")
    actual_parent = _git(root, "rev-parse", f"{target}^").stdout.strip() if SHA_RE.fullmatch(target) else ""
    tree = _git(root, "show", "-s", "--format=%T", target).stdout.strip() if SHA_RE.fullmatch(target) else ""
    if actual_parent != parent: errors.append("commit_parent_mismatch")
    if tree != verified_commit_closure.get("tree_sha"): errors.append("commit_tree_mismatch")
    try: remote_url = _remote_url(root, remote)
    except GovernedPushError as exc: errors.append(exc.code); remote_url = None
    closure_id = verified_commit_closure.get("verified_commit_closure_id")
    body = {"schema": PREPARATION_SCHEMA, "commit_verification_closure_id": closure_id,
            "repository": snap["repository_identity"],
            "repository_id": snap["repository_identity"].get("repository_root"), "remote": remote, "remote_name": remote,
            "remote_url": remote_url, "branch": branch, "local_head": snap["head"],
            "target_commit": target, "commit_sha": target, "parent_commit": parent, "parent_sha": parent,
            "tree_sha": tree,
            "push_operation": {"remote": remote, "source": target, "destination": f"refs/heads/{branch}", "commit_count": 1},
            "preparation_status": "prepared" if not errors else "blocked", "reason_codes": sorted(set(errors)),
            "authority": NO_AUTHORITY}
    return canon(body, "push_fingerprint", "push_preparation_id", "engineering-push-preparation-")


def verify_remote(preparation: Mapping[str, Any], *, workspace_root: str | Path = ".",
                  phase: str = "before_push", expected_commit: str | None = None) -> dict[str, Any]:
    root = Path(workspace_root).resolve(); errors = []
    if preparation.get("preparation_status") != "prepared": errors.append("push_preparation_invalid")
    exists, remote_head = _remote_head(root, str(preparation.get("remote", "")), str(preparation.get("branch", "")))
    target = str(preparation.get("target_commit", "")); parent = str(preparation.get("parent_commit", ""))
    if not exists: errors.append("remote_branch_missing")
    if phase == "before_push":
        if remote_head != parent: errors.append("multiple_commits_or_remote_changed")
        if exists and _git(root, "merge-base", "--is-ancestor", str(remote_head), target, check=False).returncode: errors.append("non_fast_forward")
        count = _git(root, "rev-list", "--count", f"{remote_head}..{target}", check=False).stdout.strip() if remote_head else ""
        if count != "1": errors.append("multiple_commits_forbidden")
    elif phase == "after_push":
        wanted = expected_commit or target
        if remote_head != wanted: errors.append("remote_head_mismatch")
    else: errors.append("invalid_verification_phase")
    body = {"schema": REMOTE_VERIFICATION_SCHEMA, "push_preparation_reference": _ref(preparation),
            "commit_verification_closure_id": preparation.get("commit_verification_closure_id"),
            "phase": phase, "remote": preparation.get("remote"), "branch": preparation.get("branch"),
            "branch_exists": exists, "remote_head": remote_head, "target_commit": target,
            "fast_forward_eligible": phase == "before_push" and not errors,
            "verification_status": "verified" if not errors else "failed", "reason_codes": sorted(set(errors)),
            "mutation_performed": False, "authority": NO_AUTHORITY}
    return canon(body, "remote_verification_fingerprint", "remote_verification_id", "engineering-remote-verification-")


def review_push(preparation: Mapping[str, Any], remote_verification: Mapping[str, Any], review: Mapping[str, Any]) -> dict[str, Any]:
    if not review.get("human_actor"): raise GovernedPushError("missing_human_actor")
    decision = review.get("decision")
    if decision not in {"approved", "rejected", "blocked"}: raise GovernedPushError("invalid_push_review_decision")
    errors = []
    if remote_verification.get("verification_status") != "verified": errors.append("remote_verification_not_valid")
    if remote_verification.get("push_preparation_reference") != _ref(preparation): errors.append("stale_push_preparation")
    if remote_verification.get("commit_verification_closure_id") != preparation.get("commit_verification_closure_id"): errors.append("verification_closure_id_mismatch")
    effective = decision if not errors else "blocked"
    body = {"schema": REVIEW_SCHEMA, "push_preparation_reference": _ref(preparation),
            "commit_verification_closure_id": preparation.get("commit_verification_closure_id"),
            "remote_verification_reference": _ref(remote_verification), "human_actor": review["human_actor"],
            "decision": effective, "reviewed_local_head": preparation.get("local_head"),
            "reviewed_remote_head": remote_verification.get("remote_head"), "reviewed_push_fingerprint": preparation.get("push_fingerprint"),
            "risk_acknowledgements": list(review.get("risk_acknowledgements") or []), "notes": review.get("notes", ""),
            "reason_codes": errors, "authority": NO_AUTHORITY}
    return canon(body, "push_review_fingerprint", "push_review_id", "engineering-push-review-")


def authorize_push(preparation: Mapping[str, Any], remote_verification: Mapping[str, Any], review: Mapping[str, Any], authorization: Mapping[str, Any]) -> dict[str, Any]:
    if not authorization.get("human_actor"): raise GovernedPushError("missing_authorization_actor")
    decision = authorization.get("decision")
    if decision not in {"authorized", "rejected"}: raise GovernedPushError("invalid_push_authorization_decision")
    errors = []
    if review.get("decision") != "approved": errors.append("push_review_not_approved")
    if review.get("push_preparation_reference") != _ref(preparation): errors.append("stale_push_review")
    if review.get("remote_verification_reference") != _ref(remote_verification): errors.append("stale_remote_verification")
    closure_id = preparation.get("commit_verification_closure_id")
    if not closure_id or review.get("commit_verification_closure_id") != closure_id or remote_verification.get("commit_verification_closure_id") != closure_id: errors.append("verification_closure_id_mismatch")
    if remote_verification.get("verification_status") != "verified": errors.append("remote_verification_not_valid")
    if authorization.get("confirmed_push_fingerprint") != preparation.get("push_fingerprint"): errors.append("push_fingerprint_mismatch")
    if authorization.get("confirmed_local_head") != preparation.get("local_head"): errors.append("local_head_mismatch")
    if authorization.get("confirmed_remote_head") != remote_verification.get("remote_head"): errors.append("remote_head_mismatch")
    authorized = decision == "authorized" and not errors
    body = {"schema": AUTHORIZATION_SCHEMA, "push_preparation_reference": _ref(preparation),
            "commit_verification_closure_id": closure_id,
            "remote_verification_reference": _ref(remote_verification), "push_review_reference": _ref(review),
            "human_actor": authorization["human_actor"], "decision": decision, "authorized": authorized,
            "confirmed_push_fingerprint": authorization.get("confirmed_push_fingerprint"),
            "confirmed_local_head": authorization.get("confirmed_local_head"),
            "confirmed_remote_head": authorization.get("confirmed_remote_head"), "usage_status": "unused", "use_count": 0,
            "reason_codes": sorted(set(errors)), "authority": PUSH_AUTHORITY if authorized else NO_AUTHORITY}
    return canon(body, "push_authorization_fingerprint", "push_authorization_id", "engineering-push-authorization-")


def execute_push(preparation: Mapping[str, Any], remote_before: Mapping[str, Any], review: Mapping[str, Any],
                 authorization: Mapping[str, Any], verified_commit_closure: Mapping[str, Any], *,
                 observed_at: str, workspace_root: str | Path = ".") -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(workspace_root).resolve(); errors = []
    snap = inspect_git_workspace(root)
    if review.get("decision") != "approved": errors.append("push_review_not_approved")
    if not authorization.get("authorized"): errors.append("push_not_authorized")
    if authorization.get("usage_status") != "unused": errors.append("push_authorization_replay")
    if remote_before.get("verification_status") != "verified": errors.append("remote_verification_not_valid")
    if remote_before.get("push_preparation_reference") != _ref(preparation): errors.append("stale_remote_verification")
    if review.get("push_preparation_reference") != _ref(preparation) or authorization.get("push_preparation_reference") != _ref(preparation): errors.append("stale_push_preparation")
    if authorization.get("push_review_reference") != _ref(review): errors.append("stale_push_review")
    if authorization.get("remote_verification_reference") != _ref(remote_before): errors.append("stale_remote_verification")
    closure_id = preparation.get("commit_verification_closure_id")
    if verified_commit_closure.get("status") != "verified" or verified_commit_closure.get("sealed") is not True: errors.append("verified_commit_closure_not_verified")
    if not _verified_closure_integrity_valid(verified_commit_closure): errors.append("verified_commit_closure_integrity_invalid")
    if not closure_id or verified_commit_closure.get("verified_commit_closure_id") != closure_id: errors.append("verification_closure_id_mismatch")
    if any(x.get("commit_verification_closure_id") != closure_id for x in (remote_before, review, authorization)): errors.append("verification_closure_id_mismatch")
    if verified_commit_closure.get("commit_evidence_status") != "complete": errors.append("commit_evidence_not_complete")
    if verified_commit_closure.get("commit_sha") != preparation.get("commit_sha"): errors.append("verified_commit_changed")
    actual_parent = _git(root, "rev-parse", f"{preparation.get('commit_sha')}^").stdout.strip()
    actual_tree = _git(root, "show", "-s", "--format=%T", str(preparation.get("commit_sha"))).stdout.strip()
    if actual_parent != preparation.get("parent_sha"): errors.append("commit_parent_changed")
    if actual_tree != preparation.get("tree_sha"): errors.append("commit_tree_changed")
    if actual_parent != verified_commit_closure.get("parent_sha") or actual_tree != verified_commit_closure.get("tree_sha"): errors.append("verified_commit_object_changed")
    if snap["head"] != preparation.get("local_head") or snap["branch"] != preparation.get("branch"): errors.append("local_branch_changed")
    if not snap["working_tree_clean"]: errors.append("working_tree_not_clean")
    exists, current_remote = _remote_head(root, str(preparation.get("remote", "")), str(preparation.get("branch", "")))
    if not exists or current_remote != remote_before.get("remote_head"): errors.append("remote_changed_after_review")
    try:
        if _remote_url(root, str(preparation.get("remote", ""))) != preparation.get("remote_url"): errors.append("remote_url_changed_after_review")
    except GovernedPushError as exc: errors.append(exc.code)
    errors.extend(_validate_target(str(preparation.get("remote", "")), str(preparation.get("target_commit", "")), str(preparation.get("branch", ""))))
    if preparation.get("target_commit") != authorization.get("confirmed_local_head"): errors.append("authorization_target_mismatch")
    if errors: raise GovernedPushError(sorted(set(errors))[0])
    refspec = f"{preparation['target_commit']}:refs/heads/{preparation['branch']}"
    cp = _git(root, "push", str(preparation["remote"]), refspec, check=False)
    status = "pushed" if cp.returncode == 0 else "failed"
    used = {**authorization, "usage_status": "consumed", "use_count": 1}
    execution = canon({"schema": EXECUTION_SCHEMA, "push_preparation_reference": _ref(preparation),
        "commit_verification_closure_id": closure_id,
        "remote_verification_reference": _ref(remote_before), "push_review_reference": _ref(review),
        "push_authorization_reference": _ref(authorization), "operation": "git_push_exact_commit",
        "remote": preparation["remote"], "branch": preparation["branch"], "target_commit": preparation["target_commit"],
        "refspec": refspec, "started_at": observed_at, "completed_at": observed_at, "execution_status": status,
        "return_code": cp.returncode, "stderr_summary": cp.stderr[-1000:], "retry_performed": False,
        "authority": NO_AUTHORITY}, "push_execution_fingerprint", "push_execution_id", "engineering-push-execution-")
    return used, execution


def build_push_evidence(preparation: Mapping[str, Any], execution: Mapping[str, Any], *, observed_at: str,
                        workspace_root: str | Path = ".") -> dict[str, Any]:
    exists, remote_commit = _remote_head(Path(workspace_root).resolve(), str(preparation.get("remote", "")), str(preparation.get("branch", "")))
    closure_id = preparation.get("commit_verification_closure_id")
    status = "observed" if execution.get("execution_status") == "pushed" and execution.get("push_preparation_reference") == _ref(preparation) and execution.get("commit_verification_closure_id") == closure_id and exists else "failed"
    body = {"schema": EVIDENCE_SCHEMA, "push_preparation_reference": _ref(preparation),
            "commit_verification_closure_id": closure_id,
            "push_execution_reference": _ref(execution), "pushed_commit": preparation.get("target_commit"),
            "remote_commit": remote_commit, "remote": preparation.get("remote"), "branch": preparation.get("branch"),
            "observed_at": observed_at, "evidence_status": status,
            "verification_result": "passed" if status == "observed" and remote_commit == preparation.get("target_commit") else "failed",
            "append_only": True, "authority": NO_AUTHORITY}
    return canon(body, "evidence_fingerprint", "push_evidence_id", "engineering-push-evidence-")


def close_push(preparation: Mapping[str, Any], authorization: Mapping[str, Any], execution: Mapping[str, Any],
               evidence: Mapping[str, Any], remote_after: Mapping[str, Any], *, closed_at: str) -> dict[str, Any]:
    errors = []
    if authorization.get("usage_status") != "consumed" or authorization.get("use_count") != 1: errors.append("authorization_not_consumed_once")
    if execution.get("execution_status") != "pushed": errors.append("push_not_successful")
    if evidence.get("evidence_status") != "observed": errors.append("push_evidence_invalid")
    if remote_after.get("verification_status") != "verified": errors.append("post_push_remote_verification_failed")
    if remote_after.get("remote_head") != preparation.get("target_commit"): errors.append("remote_head_mismatch")
    closure_id = preparation.get("commit_verification_closure_id")
    if not closure_id or any(x.get("commit_verification_closure_id") != closure_id for x in (authorization, execution, evidence, remote_after)): errors.append("verification_closure_id_mismatch")
    body = {"schema": CLOSURE_SCHEMA, "push_preparation_reference": _ref(preparation),
            "commit_verification_closure_id": closure_id,
            "push_authorization_reference": _ref(authorization), "push_execution_reference": _ref(execution),
            "push_evidence_reference": _ref(evidence), "remote_verification_reference": _ref(remote_after),
            "target_commit": preparation.get("target_commit"), "remote_commit": remote_after.get("remote_head"),
            "repository_id": preparation.get("repository_id"), "remote_name": preparation.get("remote_name"),
            "remote_url": preparation.get("remote_url"), "source_branch": preparation.get("branch"),
            "pushed_commit_sha": preparation.get("target_commit"), "verified_remote_commit_sha": remote_after.get("remote_head"),
            "closed_at": closed_at, "closure_status": "closed" if not errors else "failed",
            "sealed": not errors,
            "reason_codes": sorted(set(errors)), "next_governed_action": "push_complete" if not errors else "requires_human_push_review",
            "no_pr_created": True, "no_merge_performed": True, "no_tag_created": True, "no_release_created": True,
            "authority": NO_AUTHORITY}
    return canon(body, "push_closure_fingerprint", "push_closure_id", "engineering-push-closure-")


def inspect_push_state(bundle: Mapping[str, Any]) -> dict[str, Any]:
    get = lambda key: bundle.get(STORE_FILES[key]) or {}
    closure = get("closure")
    return {"schema": "zero.engineering.push_state.v1", "verified_commit_closure_status": get("verified_commit_closure").get("status", "not_started"),
            "push_preparation_status": get("preparation").get("preparation_status", "not_started"),
            "remote_verification_status": get("remote_before").get("verification_status", "not_started"),
            "human_push_review_status": get("review").get("decision", "not_started"),
            "push_authorization_status": "authorized" if get("authorization").get("authorized") else "not_authorized",
            "push_execution_status": get("execution").get("execution_status", "not_started"),
            "push_evidence_status": get("evidence").get("evidence_status", "not_started"),
            "post_push_verification_status": get("remote_after").get("verification_status", "not_started"),
            "push_closure_status": closure.get("closure_status", "not_started"),
            "next_governed_action": closure.get("next_governed_action", "prepare-push"),
            **{f"will_{x}": False for x in ("push", "retry", "pull", "merge", "rebase", "create_pr", "tag", "release")}}


def resume_push_state(bundle: Mapping[str, Any]) -> dict[str, Any]:
    state = inspect_push_state(bundle)
    if bundle.get(STORE_FILES["closure"]): action = state["next_governed_action"]
    elif bundle.get(STORE_FILES["remote_after"]): action = "close-push"
    elif bundle.get(STORE_FILES["evidence"]): action = "verify-push-remote"
    elif bundle.get(STORE_FILES["execution"]): action = "push-evidence"
    elif bundle.get(STORE_FILES["authorization"]): action = "execute-push"
    elif bundle.get(STORE_FILES["review"]): action = "authorize-push"
    elif bundle.get(STORE_FILES["remote_before"]): action = "review-push"
    elif bundle.get(STORE_FILES["preparation"]): action = "verify-push-remote-before"
    elif bundle.get(STORE_FILES["verified_commit_closure"]): action = "prepare-push"
    else: action = "close-verified-commit"
    return {**state, "decision": action, "next_governed_action": action}

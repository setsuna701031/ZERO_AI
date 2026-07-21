from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.engineering.engineering_governed_patch_authorization import AUTHORITY
from core.engineering.engineering_multifile_coding_workflow import canon
from core.engineering.engineering_practical_task_runner import _ref, safe_path

PREPARATION_SCHEMA = "zero.engineering.commit_preparation_intake.v1"
CANDIDATE_SCHEMA = "zero.engineering.commit_candidate.v1"
DIFF_SCHEMA = "zero.engineering.commit_diff_verification.v1"
ADMISSION_SCHEMA = "zero.engineering.commit_admission.v1"
REQUEST_SCHEMA = "zero.engineering.explicit_commit_request.v1"
EVIDENCE_SCHEMA = "zero.engineering.commit_evidence.v1"
VERIFICATION_SCHEMA = "zero.engineering.commit_verification.v1"
STORE_FILES = {
    "preparation": "commit/preparation-intake.json",
    "candidate": "commit/candidate.json",
    "diff_verification": "commit/diff-verification.json",
    "admission": "commit/admission.json",
    "request": "commit/request.json",
    "evidence": "commit/evidence.json",
    "verification": "commit/verification.json",
}
NO_AUTHORITY = {"may_commit": False, "may_push": False, "may_create_pr": False,
                "may_merge": False, "may_tag": False, "may_release": False}


class GovernedCommitError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=root, text=True, encoding="utf-8",
                            errors="replace", capture_output=True, shell=False)
    if check and result.returncode:
        raise GovernedCommitError("git_inspection_failed")
    return result


def _lines(value: str) -> list[str]:
    return [line.rstrip() for line in value.splitlines() if line.strip()]


def inspect_git_workspace(workspace_root: str | Path = ".") -> dict[str, Any]:
    root = Path(workspace_root).resolve()
    branch = _git(root, "branch", "--show-current").stdout.strip()
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    top = Path(_git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top != root:
        raise GovernedCommitError("repository_root_mismatch")
    status = _lines(_git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout)
    changed = sorted({line[3:].replace("\\", "/") for line in status})
    staged = sorted({line[3:].replace("\\", "/") for line in status if line[0] not in {" ", "?"}})
    unstaged = sorted({line[3:].replace("\\", "/") for line in status if line[1] not in {" ", "?"}})
    untracked = sorted({line[3:].replace("\\", "/") for line in status if line.startswith("??")})
    return {"repository_identity": {"repository_root": str(top), "git_dir": str((top / ".git").resolve())},
            "branch": branch, "head": head, "status_lines": status, "changed_paths": changed,
            "staged_paths": staged, "unstaged_paths": unstaged, "untracked_paths": untracked,
            "working_tree_clean": not status}


def _diff_bytes(root: Path, paths: Sequence[str], *, cached: bool = False,
                parent: str | None = None) -> bytes:
    args = ["diff"]
    if cached:
        args.append("--cached")
    if parent:
        args.append(parent)
    args.extend(["--", *paths])
    cp = subprocess.run(["git", *args], cwd=root, capture_output=True, shell=False)
    if cp.returncode:
        raise GovernedCommitError("git_diff_failed")
    return cp.stdout


def _fingerprint(root: Path, paths: Sequence[str]) -> str:
    tracked = _diff_bytes(root, paths)
    chunks = [tracked]
    for rel in sorted(paths):
        path = safe_path(root, rel)
        if not _git(root, "ls-files", "--error-unmatch", "--", rel, check=False).returncode:
            continue
        if path.is_file():
            chunks.extend([rel.encode(), b"\0", path.read_bytes(), b"\0"])
    return hashlib.sha256(b"".join(chunks)).hexdigest()


def _valid_message(message: str) -> bool:
    return bool(message and len(message) <= 200 and "\n" not in message and "\r" not in message
                and not re.search(r"(?i)(token|password|secret)\s*[:=]|https?://[^\s]*@", message))


def build_commit_preparation_intake(completion_review: Mapping[str, Any], apply_result: Mapping[str, Any],
                                    verification_result: Mapping[str, Any], authorized_package: Mapping[str, Any],
                                    authorization_usage: Mapping[str, Any], *, workspace_root: str | Path = ".",
                                    session_id: str | None = None, iteration_reference: Any = None) -> dict[str, Any]:
    snap = inspect_git_workspace(workspace_root)
    changed = list(apply_result.get("changed_paths") or [])
    authorized = list(authorized_package.get("ordered_paths") or authorized_package.get("authorized_paths") or [])
    errors = []
    if completion_review.get("decision") != "completed": errors.append("completion_review_not_completed")
    if apply_result.get("mutation_status") != "applied": errors.append("apply_result_not_applied")
    if verification_result.get("verification_status") != "passed" or not verification_result.get("completion_eligible"): errors.append("verification_not_passed")
    if authorization_usage.get("authorization_usage") != "consumed": errors.append("authorization_usage_mismatch")
    if sorted(changed) != sorted(authorized): errors.append("authorized_path_mismatch")
    if sorted(snap["changed_paths"]) != sorted(changed): errors.append("workspace_drift")
    body = {"schema": PREPARATION_SCHEMA, "completion_review_reference": _ref(completion_review),
            "apply_result_reference": _ref(apply_result), "verification_result_reference": _ref(verification_result),
            "authorized_change_package_reference": _ref(authorized_package),
            "authorization_usage_reference": _ref(authorization_usage), "repository_identity": snap["repository_identity"],
            "session_id": session_id or authorized_package.get("session_id"),
            "iteration_reference": iteration_reference if iteration_reference is not None else authorized_package.get("iteration_reference"),
            "pre_apply_head": authorized_package.get("pre_apply_head", snap["head"]), "current_head": snap["head"],
            "workspace_snapshot": snap, "changed_paths": changed, "authorized_paths": authorized,
            "operation_ids": [x.get("operation_id") for x in authorized_package.get("ordered_operations", [])],
            "verification_targets": list(authorized_package.get("verification_plan", {}).get("targets") or []),
            "commit_constraints": {"exact_paths_only": True, "single_use": True, "no_amend": True},
            "preparation_status": "prepared" if not errors else "blocked", "reason_codes": sorted(set(errors)),
            "authority": NO_AUTHORITY}
    return canon(body, "commit_preparation_fingerprint", "commit_preparation_id", "engineering-commit-preparation-")


def build_commit_candidate(preparation: Mapping[str, Any], *, commit_message: str,
                           commit_body: str = "", workspace_root: str | Path = ".",
                           excluded_paths: Sequence[str] = ()) -> dict[str, Any]:
    if preparation.get("preparation_status") != "prepared": raise GovernedCommitError("commit_preparation_not_ready")
    if not _valid_message(commit_message): raise GovernedCommitError("invalid_commit_message")
    if re.search(r"(?im)^(co-authored-by|signed-off-by):", commit_body): raise GovernedCommitError("prohibited_commit_metadata")
    root = Path(workspace_root).resolve(); paths = list(preparation.get("changed_paths") or [])
    body = {"schema": CANDIDATE_SCHEMA, "commit_preparation_reference": _ref(preparation),
            "pre_commit_head": preparation.get("current_head"), "repository_identity": preparation.get("repository_identity"),
            "workspace_snapshot_reference": _ref(preparation.get("workspace_snapshot", {})),
            "authorized_change_package_reference": preparation.get("authorized_change_package_reference"),
            "apply_result_reference": preparation.get("apply_result_reference"),
            "verification_result_reference": preparation.get("verification_result_reference"),
            "completion_review_reference": preparation.get("completion_review_reference"), "changed_paths": paths,
            "diff_fingerprint": _fingerprint(root, paths), "diff_summary": _git(root, "diff", "--stat", "--", *paths).stdout.strip(),
            "commit_message_candidate": commit_message, "commit_body_candidate": commit_body,
            "included_paths": paths, "excluded_paths": list(excluded_paths), "authority": NO_AUTHORITY}
    return canon(body, "commit_candidate_fingerprint", "commit_candidate_id", "engineering-commit-candidate-")


def verify_commit_diff(candidate: Mapping[str, Any], preparation: Mapping[str, Any], *, workspace_root: str | Path = ".") -> dict[str, Any]:
    root = Path(workspace_root).resolve(); snap = inspect_git_workspace(root); errors = []
    expected = list(candidate.get("included_paths") or [])
    if sorted(snap["changed_paths"]) != sorted(expected): errors.append("unexpected_changed_path" if set(snap["changed_paths"])-set(expected) else "missing_expected_path")
    if snap["untracked_paths"]: errors.append("untracked_file_present")
    if snap["staged_paths"]: errors.append("staged_unstaged_mismatch")
    if any(p.startswith(".zero/") or "/commit/" in p for p in expected): errors.append("session_artifact_included")
    if snap["head"] != candidate.get("pre_commit_head"): errors.append("head_mismatch")
    actual = _fingerprint(root, expected)
    if actual != candidate.get("diff_fingerprint"): errors.append("diff_fingerprint_mismatch")
    check = _git(root, "diff", "--check", "--", *expected, check=False)
    if check.returncode: errors.append("diff_check_failed")
    body = {"schema": DIFF_SCHEMA, "commit_candidate_reference": _ref(candidate),
            "commit_preparation_reference": _ref(preparation), "repository_identity": snap["repository_identity"],
            "head": snap["head"], "changed_paths": snap["changed_paths"], "staged_paths": snap["staged_paths"],
            "untracked_paths": snap["untracked_paths"], "diff_fingerprint": actual,
            "verification_status": "verified" if not errors else "blocked", "reason_codes": sorted(set(errors)),
            "authority": NO_AUTHORITY}
    return canon(body, "diff_verification_fingerprint", "diff_verification_id", "engineering-commit-diff-verification-")


def admit_commit(preparation: Mapping[str, Any], candidate: Mapping[str, Any], diff_verification: Mapping[str, Any],
                 completion_review: Mapping[str, Any], authorization_usage: Mapping[str, Any]) -> dict[str, Any]:
    errors = []
    if completion_review.get("decision") != "completed": errors.append("stale_completion_review")
    if preparation.get("preparation_status") != "prepared": errors.append("invalid_commit_preparation")
    if diff_verification.get("verification_status") != "verified": errors.append("invalid_diff_verification")
    if diff_verification.get("commit_candidate_reference") != _ref(candidate): errors.append("stale_commit_candidate")
    if authorization_usage.get("authorization_usage") != "consumed": errors.append("authorization_usage_mismatch")
    if not _valid_message(str(candidate.get("commit_message_candidate", ""))): errors.append("invalid_commit_message")
    body = {"schema": ADMISSION_SCHEMA, "commit_preparation_reference": _ref(preparation),
            "commit_candidate_reference": _ref(candidate), "diff_verification_reference": _ref(diff_verification),
            "completion_review_reference": _ref(completion_review), "authorization_usage_reference": _ref(authorization_usage),
            "repository_identity": candidate.get("repository_identity"), "confirmed_head": candidate.get("pre_commit_head"),
            "confirmed_paths": candidate.get("included_paths", []), "confirmed_diff_fingerprint": candidate.get("diff_fingerprint"),
            "admission_status": "admitted" if not errors else "blocked", "reason_codes": sorted(set(errors)),
            "replay_status": "unused", "authority": NO_AUTHORITY}
    return canon(body, "commit_admission_fingerprint", "commit_admission_id", "engineering-commit-admission-")


def build_explicit_commit_request(candidate: Mapping[str, Any], admission: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    if not request.get("human_actor"): raise GovernedCommitError("missing_human_actor")
    decision = request.get("decision")
    if decision not in {"confirmed", "rejected", "requires_revision"}: raise GovernedCommitError("invalid_commit_decision")
    body = {"schema": REQUEST_SCHEMA, "commit_candidate_reference": _ref(candidate),
            "commit_admission_reference": _ref(admission), "human_actor": request["human_actor"], "decision": decision,
            "confirmed_commit_message": request.get("confirmed_commit_message"), "confirmed_commit_body": request.get("confirmed_commit_body", ""),
            "confirmed_paths": list(request.get("confirmed_paths") or []),
            "confirmed_diff_fingerprint": request.get("confirmed_diff_fingerprint"), "confirmed_head": request.get("confirmed_head"),
            "risk_acknowledgements": list(request.get("risk_acknowledgements") or []), "notes": request.get("notes", ""),
            "authority": {**NO_AUTHORITY, "may_commit": decision == "confirmed"}}
    return canon(body, "explicit_commit_request_fingerprint", "explicit_commit_request_id", "engineering-explicit-commit-request-")


def _request_errors(request: Mapping[str, Any], admission: Mapping[str, Any], candidate: Mapping[str, Any], snap: Mapping[str, Any], actual_fp: str) -> list[str]:
    errors = []
    if request.get("decision") != "confirmed": errors.append("commit_request_not_confirmed")
    if admission.get("admission_status") != "admitted": errors.append("commit_not_admitted")
    if request.get("commit_candidate_reference") != _ref(candidate): errors.append("stale_commit_candidate")
    if request.get("commit_admission_reference") != _ref(admission): errors.append("stale_commit_admission")
    if request.get("confirmed_head") != snap.get("head"): errors.append("head_mismatch")
    if request.get("confirmed_diff_fingerprint") != actual_fp: errors.append("diff_fingerprint_mismatch")
    if request.get("confirmed_paths") != candidate.get("included_paths"): errors.append("path_substitution")
    if request.get("confirmed_commit_message") != candidate.get("commit_message_candidate"): errors.append("commit_message_substitution")
    if admission.get("replay_status") != "unused": errors.append("commit_admission_replay")
    if request.get("usage_status", "unused") != "unused": errors.append("commit_request_replay")
    return errors


def execute_governed_commit(request: Mapping[str, Any], admission: Mapping[str, Any], candidate: Mapping[str, Any], *, workspace_root: str | Path = ".") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = Path(workspace_root).resolve(); snap = inspect_git_workspace(root); paths = list(request.get("confirmed_paths") or [])
    actual_fp = _fingerprint(root, paths); errors = _request_errors(request, admission, candidate, snap, actual_fp)
    if snap["staged_paths"] or snap["untracked_paths"] or sorted(snap["changed_paths"]) != sorted(paths): errors.append("workspace_drift")
    if errors: raise GovernedCommitError(sorted(set(errors))[0])
    _git(root, "add", "--", *paths)
    if sorted(inspect_git_workspace(root)["staged_paths"]) != sorted(paths): raise GovernedCommitError("staged_path_mismatch")
    args = ["commit", "-m", str(request["confirmed_commit_message"])]
    if request.get("confirmed_commit_body"): args.extend(["-m", str(request["confirmed_commit_body"])])
    cp = _git(root, *args, check=False)
    if cp.returncode: raise GovernedCommitError("git_commit_failed")
    post = inspect_git_workspace(root); sha = post["head"]
    evidence = canon({"schema": EVIDENCE_SCHEMA, "explicit_commit_request_reference": _ref(request),
        "commit_admission_reference": _ref(admission), "commit_candidate_reference": _ref(candidate),
        "pre_commit_head": snap["head"], "post_commit_head": sha, "commit_sha": sha,
        "commit_message": request["confirmed_commit_message"], "committed_paths": paths,
        "diff_fingerprint": actual_fp, "repository_identity": snap["repository_identity"], "commit_status": "committed",
        "limitations": [], "authority": NO_AUTHORITY}, "commit_evidence_fingerprint", "commit_evidence_id", "engineering-commit-evidence-")
    used_request = {**request, "usage_status": "consumed", "use_count": 1}
    used_admission = {**admission, "replay_status": "used"}
    return used_request, used_admission, evidence


def verify_commit(evidence: Mapping[str, Any], request: Mapping[str, Any], *, workspace_root: str | Path = ".") -> dict[str, Any]:
    root = Path(workspace_root).resolve(); snap = inspect_git_workspace(root); errors = []
    sha = str(evidence.get("commit_sha", "")); parent = _git(root, "rev-parse", f"{sha}^").stdout.strip()
    paths = sorted(_lines(_git(root, "show", "--pretty=format:", "--name-only", sha).stdout))
    message = _git(root, "show", "-s", "--format=%s", sha).stdout.strip()
    fp = hashlib.sha256(_diff_bytes(root, list(evidence.get("committed_paths") or []), parent=f"{parent}..{sha}")).hexdigest()
    if snap["head"] != sha or evidence.get("post_commit_head") != sha: errors.append("post_commit_head_mismatch")
    if parent != evidence.get("pre_commit_head"): errors.append("commit_parent_mismatch")
    if paths != sorted(request.get("confirmed_paths") or []): errors.append("committed_path_mismatch")
    if message != request.get("confirmed_commit_message"): errors.append("commit_message_substitution")
    if not snap["working_tree_clean"]: errors.append("working_tree_not_clean")
    if fp != evidence.get("diff_fingerprint"): errors.append("diff_fingerprint_mismatch")
    body = {"schema": VERIFICATION_SCHEMA, "commit_evidence_reference": _ref(evidence),
            "explicit_commit_request_reference": _ref(request), "post_commit_head": snap["head"], "commit_sha": sha,
            "commit_parent": parent, "committed_paths": paths, "working_tree_clean": snap["working_tree_clean"],
            "no_untracked_files": not snap["untracked_paths"], "push_performed": False, "remote_changed": False,
            "diff_fingerprint": fp, "verification_status": "verified" if not errors else "failed",
            "reason_codes": sorted(set(errors)), "next_governed_action": "awaiting_explicit_push_review" if not errors else "requires_commit_review",
            "authority": NO_AUTHORITY}
    return canon(body, "commit_verification_fingerprint", "commit_verification_id", "engineering-commit-verification-")


def inspect_commit_state(bundle: Mapping[str, Any]) -> dict[str, Any]:
    get = lambda key: bundle.get(STORE_FILES[key]) or {}
    verification = get("verification")
    return {"schema": "zero.engineering.commit_state.v1", "commit_preparation_status": get("preparation").get("preparation_status", "not_started"),
            "commit_candidate_status": "prepared" if get("candidate") else "not_started",
            "diff_verification_status": get("diff_verification").get("verification_status", "not_started"),
            "commit_admission_status": get("admission").get("admission_status", "not_started"),
            "explicit_commit_request_status": get("request").get("decision", "not_started"),
            "commit_execution_status": get("evidence").get("commit_status", "not_started"),
            "commit_verification_status": verification.get("verification_status", "not_started"),
            "push_status": "not_performed", "next_governed_action": verification.get("next_governed_action", "prepare-commit"),
            **{f"will_{x}": False for x in ("commit", "push", "create_pr", "merge", "tag", "release", "retry", "complete")}}


def resume_commit_state(bundle: Mapping[str, Any]) -> dict[str, Any]:
    state = inspect_commit_state(bundle)
    if bundle.get(STORE_FILES["verification"]): action = state["next_governed_action"]
    elif bundle.get(STORE_FILES["evidence"]): action = "verify-commit"
    elif bundle.get(STORE_FILES["request"]): action = "execute-commit"
    elif bundle.get(STORE_FILES["admission"]): action = "confirm-commit"
    elif bundle.get(STORE_FILES["diff_verification"]): action = "admit-commit"
    elif bundle.get(STORE_FILES["candidate"]): action = "validate-commit-candidate"
    elif bundle.get(STORE_FILES["preparation"]): action = "commit-candidate"
    else: action = "prepare-commit"
    return {**state, "decision": action, "next_governed_action": action}

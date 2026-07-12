from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping


RUNTIME_EXECUTION_PLAN_REVIEW_GATE_CONTRACT = "zero.runtime.execution_plan_review_gate.v1"
RUNTIME_EXECUTION_PLAN_OPERATOR_REVIEW_CONTRACT = "zero.runtime.execution_plan_operator_review.v1"
_PLAN_SCHEMA = "zero.runtime.apply_execution_plan.v1"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_EVIDENCE = [
    "approval_audit_record_required", "admission_audit_record_required",
    "proposal_fingerprint_required", "pre_execution_snapshot_evidence_required",
    "post_execution_validation_evidence_required", "changed_files_evidence_required",
    "rollback_evidence_required",
]
_CONSTRAINTS = {
    "controlled_mode_required": True, "allowed_files_only": True,
    "scope_expansion_allowed": False, "goal_mutation_allowed": False,
    "requested_changes_modification_allowed": False,
    "autonomous_task_creation_allowed": False, "patch_generation_allowed": False,
    "direct_filesystem_access_allowed": False,
    "governed_mutation_adapter_required": True, "validation_required": True,
    "rollback_required": True, "operator_approval_required": True,
    "admission_required": True,
}
_SECURITY = {
    "execution_started": False, "mutation_started": False,
    "mutation_allowed": False, "patch_generation_allowed": False,
    "patch_application_allowed": False, "autonomous_apply_allowed": False,
    "requires_controlled_executor": True,
    "requires_separate_execution_step": True,
    "requires_post_execution_validation": True,
    "requires_rollback_capability": True,
}
_DANGEROUS = {
    "auto_approve": True, "executor_override": True, "skip_validation": True,
    "rollback_disabled": True, "scope_expansion": True,
    "uncontrolled_execution": True, "mutation_allowed": True,
    "execution_allowed": True, "bypass_review": True,
    "bypass_admission": True, "bypass_operator": True,
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = _text(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _time_text(value: Any) -> str:
    return _parse_time(value).replace(microsecond=0).isoformat()


def _safe_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip().replace("\\", "/")
    if text in {".", "/"} or "*" in text or "?" in text or Path(text).is_absolute():
        return False
    path = PurePosixPath(text)
    return not path.is_absolute() and ".." not in path.parts and all(part for part in path.parts)


def _unique_paths(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    result: list[str] = []
    for item in value:
        if not _safe_path(item):
            return None
        normalized = item.strip().replace("\\", "/")
        if normalized not in result:
            result.append(normalized)
    return result


def _dangerous(value: Any) -> str:
    if isinstance(value, Mapping):
        for key, unsafe in _DANGEROUS.items():
            if value.get(key) is unsafe:
                return key
        for child in value.values():
            found = _dangerous(child)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for child in value:
            found = _dangerous(child)
            if found:
                return found
    return ""


def _base(review: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "contract": RUNTIME_EXECUTION_PLAN_REVIEW_GATE_CONTRACT,
        "result_id": "", "review_id": _text(review.get("review_id")),
        "plan_id": _text(review.get("plan_id")),
        "operator_id": _text(review.get("operator_id")),
        "review_status": "invalid", "review_valid": False,
        "decision_accepted": False, "gate_passed": False,
        "executor_admission_ready": False, "execution_allowed": False,
        "reviewed_at": _text(review.get("reviewed_at")),
        "expires_at": _text(review.get("expires_at")), "reasons": [],
        "validated_identity_chain": {}, "validated_scope": [],
        "validated_constraints": {}, "validated_security_invariants": {},
        "validated_evidence_requirements": [], "audit_record": {},
    }


def review_execution_plan(execution_plan: Mapping[str, Any],
                          operator_review: Mapping[str, Any], *,
                          now: Any = None) -> dict[str, Any]:
    plan_is_mapping = isinstance(execution_plan, Mapping)
    review_is_mapping = isinstance(operator_review, Mapping)
    plan = _mapping(execution_plan)
    review = _mapping(operator_review)
    result = _base(review)
    reasons: list[str] = []

    if not plan_is_mapping: reasons.append("execution_plan_object_required")
    if not review_is_mapping: reasons.append("operator_review_object_required")
    if plan.get("schema") != _PLAN_SCHEMA: reasons.append("invalid_execution_plan_schema")
    if review.get("contract", review.get("schema")) != RUNTIME_EXECUTION_PLAN_OPERATOR_REVIEW_CONTRACT:
        reasons.append("invalid_operator_review_contract")
    for key in ("review_id", "plan_id", "operator_id"):
        if not _text(review.get(key)): reasons.append(f"{key}_required")
    decision = review.get("decision")
    if not isinstance(decision, str) or decision not in {"approved", "rejected"}:
        reasons.append("invalid_decision")

    reviewed_at = expires_at = current = None
    try: reviewed_at = _parse_time(review.get("reviewed_at"))
    except (TypeError, ValueError): reasons.append("invalid_reviewed_at")
    try: expires_at = _parse_time(review.get("expires_at"))
    except (TypeError, ValueError): reasons.append("invalid_expires_at")
    try: current = _parse_time(now if now is not None else datetime.now(timezone.utc))
    except (TypeError, ValueError): reasons.append("invalid_now")
    if reviewed_at and expires_at and expires_at <= reviewed_at:
        reasons.append("expiration_not_after_review")
    if current and expires_at and current >= expires_at:
        reasons.append("review_expired")

    if plan.get("plan_status") != "ready" or plan.get("plan_ready") is not True or plan.get("ok") is not True:
        reasons.append("execution_plan_not_reviewable")
    identity = {key: _text(plan.get(key)) for key in
                ("proposal_id", "approval_id", "admission_id", "plan_id")}
    for key, value in identity.items():
        if not value: reasons.append(f"plan_{key}_required")
    plan_audit = _mapping(plan.get("audit_record"))
    for key in ("proposal_id", "approval_id", "admission_id", "plan_id"):
        if _text(plan_audit.get(key)) != identity[key]:
            reasons.append(f"{key}_chain_mismatch")
    if _text(review.get("plan_id")) != identity["plan_id"]:
        reasons.append("plan_id_mismatch")

    fingerprint_keys = ("proposal_fingerprint", "approval_proposal_fingerprint",
                        "scope_fingerprint", "approval_scope_fingerprint",
                        "admission_scope_fingerprint")
    fingerprints = {key: _text(plan.get(key)) for key in fingerprint_keys}
    if any(not _HEX_64.fullmatch(value) for value in fingerprints.values()):
        reasons.append("invalid_fingerprint")
    if fingerprints["proposal_fingerprint"] != fingerprints["approval_proposal_fingerprint"]:
        reasons.append("proposal_fingerprint_mismatch")
    if _text(plan_audit.get("proposal_fingerprint")) != fingerprints["proposal_fingerprint"]:
        reasons.append("proposal_fingerprint_audit_mismatch")
    if len({fingerprints[key] for key in fingerprint_keys[2:]}) != 1:
        reasons.append("scope_fingerprint_mismatch")
    if _text(plan_audit.get("scope_fingerprint")) != fingerprints["scope_fingerprint"]:
        reasons.append("scope_fingerprint_audit_mismatch")

    allowed = _unique_paths(plan.get("allowed_files"))
    if allowed is None: reasons.append("invalid_allowed_files")
    elif allowed != plan.get("allowed_files"): reasons.append("allowed_files_not_stable_deduplicated")
    scope = _mapping(plan.get("allowed_scope"))
    scope_paths = _unique_paths(scope.get("target_files"))
    if scope_paths is None: reasons.append("invalid_admission_scope")
    elif allowed is not None and any(path not in scope_paths for path in allowed):
        reasons.append("allowed_files_outside_admission_scope")
    acknowledged = _unique_paths(review.get("acknowledged_scope"))
    if acknowledged is None or acknowledged != (allowed or []):
        reasons.append("acknowledged_scope_mismatch")

    constraints = _mapping(plan.get("execution_constraints"))
    if constraints != _CONSTRAINTS: reasons.append("invalid_execution_constraints")
    if not isinstance(review.get("acknowledged_constraints"), Mapping) or _mapping(review.get("acknowledged_constraints")) != constraints:
        reasons.append("acknowledged_constraints_mismatch")
    security = {key: plan.get(key) for key in _SECURITY}
    if security != _SECURITY or plan.get("controlled") is not True or plan.get("decision_authority") is not False:
        reasons.append("invalid_security_invariants")
    if not isinstance(review.get("acknowledged_security_invariants"), Mapping) or _mapping(review.get("acknowledged_security_invariants")) != security:
        reasons.append("acknowledged_security_invariants_mismatch")
    unsafe = _dangerous({"plan": plan, "review": review})
    if unsafe: reasons.append(f"unsafe_override:{unsafe}")

    evidence = plan.get("evidence_requirements")
    if evidence != _EVIDENCE: reasons.append("invalid_evidence_requirements")
    if review.get("acknowledged_evidence_requirements") != evidence:
        reasons.append("acknowledged_evidence_requirements_mismatch")

    valid = not reasons
    rejected = valid and decision == "rejected"
    approved = valid and decision == "approved"
    result.update({
        "review_status": "approved" if approved else "rejected" if rejected else "invalid",
        "review_valid": valid, "decision_accepted": valid,
        "gate_passed": approved, "executor_admission_ready": approved,
        "execution_allowed": False, "reasons": reasons,
        "validated_identity_chain": identity if valid else {},
        "validated_scope": allowed if valid else [],
        "validated_constraints": constraints if valid else {},
        "validated_security_invariants": security if valid else {},
        "validated_evidence_requirements": deepcopy(evidence) if valid else [],
    })
    seed = {"review_id": result["review_id"], "plan_id": result["plan_id"],
            "operator_id": result["operator_id"], "decision": decision,
            "reviewed_at": result["reviewed_at"], "expires_at": result["expires_at"],
            "reasons": reasons}
    result["result_id"] = f"plan-review-{_fingerprint(seed)[:16]}"
    result["audit_record"] = {
        "event_type": "execution_plan_review_evaluated", "result_id": result["result_id"],
        "review_id": result["review_id"], "plan_id": result["plan_id"],
        "operator_id": result["operator_id"], "review_status": result["review_status"],
        "review_valid": result["review_valid"], "gate_passed": result["gate_passed"],
        "executor_admission_ready": result["executor_admission_ready"],
        "execution_allowed": False, "reasons": deepcopy(reasons),
    }
    return result


__all__ = ["RUNTIME_EXECUTION_PLAN_OPERATOR_REVIEW_CONTRACT",
           "RUNTIME_EXECUTION_PLAN_REVIEW_GATE_CONTRACT", "review_execution_plan"]

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


RUNTIME_EXECUTOR_ADMISSION_TOKEN_CONTRACT = "zero.runtime.executor_admission_token.v1"
RUNTIME_OPERATOR_EXECUTION_REQUEST_CONTRACT = "zero.runtime.operator_execution_request.v1"
_PLAN = "zero.runtime.apply_execution_plan.v1"
_REVIEW = "zero.runtime.execution_plan_review_gate.v1"


def _text(value: Any) -> str: return str(value or "").strip()
def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _canonical(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fingerprint(value: Any) -> str: return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime): result = value
    else:
        text = _text(value)
        if text.endswith("Z"): text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    if result.tzinfo is None: result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _time(value: Any) -> str: return _parse_time(value).replace(microsecond=0).isoformat()


def _safe_files(value: Any) -> list[str] | None:
    if not isinstance(value, list): return None
    result: list[str] = []
    for item in value:
        if not isinstance(item, str): return None
        text = item.strip().replace("\\", "/")
        if item != item.rstrip(" ."): return None
        path = PurePosixPath(text)
        reserved = {"CON", "PRN", "AUX", "NUL", *{f"COM{i}" for i in range(1, 10)},
                    *{f"LPT{i}" for i in range(1, 10)}}
        if (not text or text in {".", "/"} or text.startswith(("//", "\\\\", "\\\\?\\"))
                or Path(text).is_absolute() or path.is_absolute() or ".." in path.parts
                or "*" in text or "?" in text or ":" in text
                or any(part.split(".")[0].upper() in reserved for part in path.parts)): return None
        if any(existing.casefold() == text.casefold() for existing in result): return None
        result.append(text)
    return result


def _target_identity(target_root: Any) -> tuple[str, str]:
    try:
        root = Path(target_root).resolve(strict=True)
        if not root.is_dir(): return "", "target_root_not_directory"
        return str(root).replace("\\", "/").casefold(), ""
    except (OSError, RuntimeError, TypeError): return "", "invalid_target_root"


def issue_executor_admission_token(execution_plan: Mapping[str, Any],
        execution_plan_review_result: Mapping[str, Any],
        operator_execution_request: Mapping[str, Any], *, target_root: Any,
        now: Any = None) -> dict[str, Any]:
    plan, review, request = map(_mapping, (execution_plan, execution_plan_review_result,
                                          operator_execution_request))
    reasons: list[str] = []
    try: issued = _parse_time(now if now is not None else datetime.now(timezone.utc))
    except (TypeError, ValueError): issued = None; reasons.append("invalid_now")
    target_identity, target_error = _target_identity(target_root)
    if target_error: reasons.append(target_error)
    if plan.get("schema") != _PLAN or plan.get("plan_status") != "ready" or plan.get("plan_ready") is not True:
        reasons.append("invalid_execution_plan")
    if review.get("contract") != _REVIEW or review.get("review_status") != "approved" or review.get("review_valid") is not True:
        reasons.append("review_not_approved")
    if review.get("executor_admission_ready") is not True: reasons.append("review_not_executor_ready")
    if review.get("execution_allowed") is not False: reasons.append("unsafe_review_execution_authority")
    if request.get("contract", request.get("schema")) != RUNTIME_OPERATOR_EXECUTION_REQUEST_CONTRACT:
        reasons.append("invalid_operator_request_contract")
    for key in ("request_id", "review_result_id", "plan_id", "operator_id"):
        if not _text(request.get(key)): reasons.append(f"{key}_required")
    if request.get("requested_mode") != "controlled_dry_run": reasons.append("invalid_requested_mode")
    if request.get("acknowledged_dry_run") is not True or request.get("acknowledged_no_file_mutation") is not True:
        reasons.append("dry_run_safety_not_acknowledged")
    if _text(request.get("plan_id")) != _text(plan.get("plan_id")) or _text(review.get("plan_id")) != _text(plan.get("plan_id")):
        reasons.append("plan_id_mismatch")
    if _text(request.get("review_result_id")) != _text(review.get("result_id")):
        reasons.append("review_result_id_mismatch")
    if _text(request.get("operator_id")) != _text(review.get("operator_id")):
        reasons.append("operator_id_mismatch")
    identity = _mapping(review.get("validated_identity_chain"))
    if any(_text(identity.get(key)) != _text(plan.get(key))
           for key in ("proposal_id", "approval_id", "admission_id", "plan_id")):
        reasons.append("review_identity_chain_mismatch")
    if _mapping(review.get("validated_constraints")) != _mapping(plan.get("execution_constraints")):
        reasons.append("review_constraints_mismatch")
    if review.get("validated_evidence_requirements") != plan.get("evidence_requirements"):
        reasons.append("review_evidence_mismatch")
    files = _safe_files(plan.get("allowed_files"))
    if files is None or files != plan.get("allowed_files"): reasons.append("invalid_allowed_files")
    acknowledged = _safe_files(request.get("acknowledged_scope"))
    if acknowledged is None or acknowledged != (files or []): reasons.append("acknowledged_scope_mismatch")
    if review.get("validated_scope") != (files or []): reasons.append("review_scope_mismatch")
    if plan.get("execution_allowed", False) is not False or plan.get("mutation_allowed") is not False:
        reasons.append("unsafe_plan_authority")
    requested_at = request_expires = review_expires = None
    try: requested_at = _parse_time(request.get("requested_at"))
    except (TypeError, ValueError): reasons.append("invalid_requested_at")
    try: request_expires = _parse_time(request.get("expires_at"))
    except (TypeError, ValueError): reasons.append("invalid_request_expiration")
    try: review_expires = _parse_time(review.get("expires_at"))
    except (TypeError, ValueError): reasons.append("invalid_review_expiration")
    if requested_at and request_expires and request_expires <= requested_at: reasons.append("invalid_request_expiration_order")
    if issued and request_expires and issued >= request_expires: reasons.append("operator_request_expired")
    if issued and review_expires and issued >= review_expires: reasons.append("review_expired")
    expires = min([value for value in (request_expires, review_expires,
                  issued + timedelta(minutes=15) if issued else None) if value], default=None)
    issued_text, expires_text = (_time(issued) if issued else "", _time(expires) if expires else "")
    security = {
        "active_execution_ready": False, "execution_allowed": False,
        "file_mutation_allowed": False, "patch_application_allowed": False,
        "commit_allowed": False, "rollback_execution_allowed": False,
        "scope_expansion_allowed": False,
    }
    seed = {
        "proposal_id": plan.get("proposal_id"), "approval_id": plan.get("approval_id"),
        "admission_id": plan.get("admission_id"), "plan_id": plan.get("plan_id"),
        "review_result_id": review.get("result_id"), "request_id": request.get("request_id"),
        "operator_id": request.get("operator_id"), "allowed_files": files or [],
        "scope_fingerprint": plan.get("scope_fingerprint"), "plan_fingerprint": _fingerprint(plan),
        "review_fingerprint": _fingerprint(review), "issued_at": issued_text,
        "expires_at": expires_text, "target_root_identity": target_identity,
    }
    issued_ok = not reasons
    result = {
        "contract": RUNTIME_EXECUTOR_ADMISSION_TOKEN_CONTRACT,
        "token_id": f"executor-token-{_fingerprint(seed)[:16]}",
        "token_status": "issued" if issued_ok else "denied", "mode": "controlled_dry_run",
        "proposal_id": _text(plan.get("proposal_id")), "approval_id": _text(plan.get("approval_id")),
        "admission_id": _text(plan.get("admission_id")), "plan_id": _text(plan.get("plan_id")),
        "review_result_id": _text(review.get("result_id")),
        "operator_request_id": _text(request.get("request_id")), "operator_id": _text(request.get("operator_id")),
        "allowed_files": files or [], "scope_fingerprint": _text(plan.get("scope_fingerprint")),
        "plan_fingerprint": _fingerprint(plan), "review_fingerprint": _fingerprint(review),
        "issued_at": issued_text, "expires_at": expires_text,
        "target_root_identity": target_identity, "execution_constraints": _mapping(plan.get("execution_constraints")),
        "dry_run_allowed": issued_ok, "execution_entry_allowed": issued_ok,
        "validation_execution_allowed": False, "active_execution_allowed": False,
        **security, "security_invariants": security, "reasons": reasons,
    }
    result["audit_record"] = {
        "event_type": "executor_admission_token_evaluated", "token_id": result["token_id"],
        "token_status": result["token_status"], "plan_id": result["plan_id"],
        "review_result_id": result["review_result_id"], "operator_request_id": result["operator_request_id"],
        "target_root_identity": target_identity, "reasons": deepcopy(reasons), **security,
    }
    return result


__all__ = ["RUNTIME_EXECUTOR_ADMISSION_TOKEN_CONTRACT",
           "RUNTIME_OPERATOR_EXECUTION_REQUEST_CONTRACT", "issue_executor_admission_token"]

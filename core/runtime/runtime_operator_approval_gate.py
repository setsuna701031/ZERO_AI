from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping


RUNTIME_OPERATOR_APPROVAL_GATE_SCHEMA = (
    "zero.runtime.operator_approval_gate.v1"
)
_PROPOSAL_SCHEMA = "zero.runtime.change_proposal_engine.v1"
_SCOPE_KEYS = (
    "target_files",
    "recommended_actions",
    "validation_requirements",
    "rollback_requirements",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return deepcopy(list(value)) if isinstance(value, (list, tuple)) else []


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=str,
    )


def _fingerprint(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = _text(value)
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _time_text(value: Any) -> str:
    return _parse_time(value).replace(microsecond=0).isoformat()


def _safe_relative(value: Any) -> bool:
    text = _text(value).replace("\\", "/")
    if not text or Path(text).is_absolute():
        return False
    path = PurePosixPath(text)
    return not path.is_absolute() and ".." not in path.parts


def _empty_scope() -> dict[str, list[Any]]:
    return {key: [] for key in _SCOPE_KEYS}


def _proposal_scope(proposal: Mapping[str, Any]) -> dict[str, list[Any]]:
    body = _mapping(proposal.get("proposal"))
    return {key: _list(body.get(key)) for key in _SCOPE_KEYS}


def _normalize_scope(value: Mapping[str, Any] | None) -> dict[str, list[Any]]:
    payload = _mapping(value)
    return {key: _list(payload.get(key)) for key in _SCOPE_KEYS}


def _scope_subset(
    requested: Mapping[str, list[Any]], available: Mapping[str, list[Any]]
) -> bool:
    for key in _SCOPE_KEYS:
        available_items = {_canonical(item) for item in available.get(key, [])}
        if any(_canonical(item) not in available_items for item in requested.get(key, [])):
            return False
    return True


def _security_invariants() -> dict[str, bool]:
    return {
        "execution_authority_granted": False,
        "mutation_allowed": False,
        "patch_application_allowed": False,
        "autonomous_apply_allowed": False,
        "requires_controlled_apply": True,
    }


def _base_result(status: str, *, ok: bool = False) -> dict[str, Any]:
    return {
        "schema": RUNTIME_OPERATOR_APPROVAL_GATE_SCHEMA,
        "ok": ok,
        "approval_id": "",
        "proposal_id": "",
        "approval_status": status,
        "decision": "",
        "operator_id": "",
        "reason": "",
        "reviewed_at": "",
        "expires_at": None,
        "expired": False,
        "revoked": False,
        "approved_scope": _empty_scope(),
        "proposal_fingerprint": "",
        "scope_fingerprint": _fingerprint(_empty_scope()),
        "audit_record": {},
        "execution_authority_granted": False,
        "mutation_allowed": False,
        "patch_application_allowed": False,
        "repair_execution_allowed": False,
        "autonomous_apply_allowed": False,
        "decision_authority": False,
        "requested_changes_modified": False,
        "requires_controlled_apply": True,
    }


def _invalid(status: str, reason: str) -> dict[str, Any]:
    result = _base_result(status)
    result["reason"] = reason
    return result


def _validate_proposal(proposal: Mapping[str, Any]) -> str:
    if proposal.get("schema") != _PROPOSAL_SCHEMA:
        return "invalid_proposal_schema"
    if not _text(proposal.get("proposal_id")):
        return "proposal_id_required"
    if proposal.get("requires_operator_approval") is not True:
        return "operator_approval_not_required"
    if proposal.get("mutation_allowed") is not False:
        return "proposal_mutation_boundary_invalid"
    if proposal.get("autonomous_apply_allowed") is not False:
        return "proposal_autonomous_apply_boundary_invalid"
    if proposal.get("patch_generation_allowed") is not False:
        return "proposal_patch_boundary_invalid"
    if proposal.get("proposal_status") not in {
        "proposal_created", "manual_review_required", "proposal_blocked_by_safety"
    }:
        return "proposal_status_not_reviewable"
    scope = _proposal_scope(proposal)
    if any(not _safe_relative(path) for path in scope["target_files"]):
        return "proposal_target_path_invalid"
    return ""


def evaluate_expiration(
    approval_record: Mapping[str, Any], now: Any = None
) -> dict[str, Any]:
    result = _mapping(approval_record)
    expires_at = result.get("expires_at")
    if not expires_at or result.get("revoked") is True:
        return result
    try:
        expired = _parse_time(expires_at) <= _parse_time(now or _utc_now())
    except (TypeError, ValueError):
        result["ok"] = False
        result["approval_status"] = "invalid_proposal"
        result["reason"] = "invalid_expiration"
        return result
    if expired:
        result["expired"] = True
        result["approval_status"] = "expired"
        result["ok"] = False
        audit = _mapping(result.get("audit_record"))
        if audit:
            audit["approval_status"] = "expired"
            result["audit_record"] = audit
    return result


@dataclass(frozen=True)
class RuntimeOperatorApprovalGate:
    clock: Callable[[], Any] = _utc_now

    def review(
        self,
        *,
        proposal: Mapping[str, Any],
        decision: Any,
        operator_id: Any,
        reason: Any = "",
        expires_at: Any = None,
        approved_scope: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        original = _mapping(proposal)
        invalid = _validate_proposal(original)
        if invalid:
            return _invalid("invalid_proposal", invalid)
        normalized_decision = _text(decision).lower()
        if normalized_decision not in {"approve", "reject", "revoke"}:
            return _invalid("invalid_decision", "decision_not_supported")
        if normalized_decision == "revoke":
            return _invalid("invalid_decision", "use_revoke_for_approval_record")
        operator = _text(operator_id)
        if not operator:
            return _invalid("invalid_operator", "operator_id_required")
        reviewed_at = _time_text(self.clock())
        expiration_text = None
        if expires_at is not None:
            try:
                expiration_text = _time_text(expires_at)
            except (TypeError, ValueError):
                return _invalid("invalid_proposal", "invalid_expiration")

        proposal_scope = _proposal_scope(original)
        if normalized_decision == "approve":
            if original.get("proposal_status") == "proposal_blocked_by_safety":
                return _invalid("invalid_proposal", "safety_blocked_proposal")
            scope = (
                _normalize_scope(approved_scope)
                if approved_scope is not None else proposal_scope
            )
            if any(not _safe_relative(path) for path in scope["target_files"]):
                return _invalid("invalid_scope", "approved_scope_path_invalid")
            if not _scope_subset(scope, proposal_scope):
                return _invalid("invalid_scope", "approved_scope_expands_proposal")
            status = "approved"
        else:
            if not _text(reason):
                return _invalid("invalid_decision", "reject_reason_required")
            if approved_scope is not None and any(
                _list(_mapping(approved_scope).get(key)) for key in _SCOPE_KEYS
            ):
                return _invalid("invalid_scope", "reject_scope_must_be_empty")
            scope = _empty_scope()
            status = "rejected"

        if expiration_text and _parse_time(expiration_text) <= _parse_time(reviewed_at):
            status = "expired"
        proposal_fingerprint = _fingerprint(original)
        scope_fingerprint = _fingerprint(scope)
        approval_seed = {
            "proposal_id": original["proposal_id"],
            "decision": normalized_decision,
            "operator_id": operator,
            "scope_fingerprint": scope_fingerprint,
            "reviewed_at": reviewed_at,
        }
        approval_id = f"operator-approval-{_fingerprint(approval_seed)[:16]}"
        audit = {
            "event_type": "operator_approval_reviewed",
            "approval_id": approval_id,
            "proposal_id": original["proposal_id"],
            "operator_id": operator,
            "decision": normalized_decision,
            "approval_status": status,
            "reason": _text(reason),
            "reviewed_at": reviewed_at,
            "expires_at": expiration_text,
            "proposal_fingerprint": proposal_fingerprint,
            "scope_fingerprint": scope_fingerprint,
            "security_invariants": _security_invariants(),
        }
        result = _base_result(status, ok=status in {"approved", "rejected"})
        result.update({
            "approval_id": approval_id,
            "proposal_id": original["proposal_id"],
            "decision": normalized_decision,
            "operator_id": operator,
            "reason": _text(reason),
            "reviewed_at": reviewed_at,
            "expires_at": expiration_text,
            "expired": status == "expired",
            "approved_scope": scope,
            "proposal_fingerprint": proposal_fingerprint,
            "scope_fingerprint": scope_fingerprint,
            "audit_record": audit,
        })
        return result

    def revoke(
        self,
        approval_record: Mapping[str, Any],
        operator_id: Any,
        reason: Any,
    ) -> dict[str, Any]:
        original = _mapping(approval_record)
        if original.get("schema") != RUNTIME_OPERATOR_APPROVAL_GATE_SCHEMA:
            return _invalid("invalid_proposal", "invalid_approval_schema")
        if original.get("approval_status") != "approved" or original.get("revoked") is True:
            return _invalid("invalid_decision", "only_active_approval_can_be_revoked")
        operator = _text(operator_id)
        if not operator:
            return _invalid("invalid_operator", "operator_id_required")
        if not _text(reason):
            return _invalid("invalid_decision", "revoke_reason_required")
        evaluated = evaluate_expiration(original, self.clock())
        if evaluated.get("expired") is True:
            return evaluated
        reviewed_at = _time_text(self.clock())
        seed = {
            "prior_approval_id": original.get("approval_id"),
            "decision": "revoke",
            "operator_id": operator,
            "reviewed_at": reviewed_at,
        }
        result = _base_result("revoked", ok=True)
        result.update({
            "approval_id": f"operator-approval-{_fingerprint(seed)[:16]}",
            "proposal_id": _text(original.get("proposal_id")),
            "approval_status": "revoked",
            "decision": "revoke",
            "operator_id": operator,
            "reason": _text(reason),
            "reviewed_at": reviewed_at,
            "expires_at": original.get("expires_at"),
            "revoked": True,
            "approved_scope": _normalize_scope(original.get("approved_scope")),
            "proposal_fingerprint": _text(original.get("proposal_fingerprint")),
            "scope_fingerprint": _text(original.get("scope_fingerprint")),
        })
        result["audit_record"] = {
            "event_type": "operator_approval_revoked",
            "approval_id": result["approval_id"],
            "proposal_id": result["proposal_id"],
            "operator_id": operator,
            "decision": "revoke",
            "approval_status": "revoked",
            "reason": result["reason"],
            "reviewed_at": reviewed_at,
            "expires_at": result["expires_at"],
            "proposal_fingerprint": result["proposal_fingerprint"],
            "scope_fingerprint": result["scope_fingerprint"],
            "security_invariants": _security_invariants(),
        }
        return result


__all__ = [
    "RUNTIME_OPERATOR_APPROVAL_GATE_SCHEMA",
    "RuntimeOperatorApprovalGate",
    "evaluate_expiration",
]

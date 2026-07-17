from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping


RUNTIME_CONTROLLED_APPLY_ADMISSION_SCHEMA = (
    "zero.runtime.controlled_apply_admission.v1"
)
_PROPOSAL_SCHEMA = "zero.runtime.change_proposal_engine.v1"
_APPROVAL_SCHEMA = "zero.runtime.operator_approval_gate.v1"
_SCOPE_KEYS = (
    "target_files", "recommended_actions", "validation_requirements",
    "rollback_requirements",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return deepcopy(list(value)) if isinstance(value, (list, tuple)) else []


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        value = _text(value)
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _time_text(value: Any) -> str:
    return _parse_time(value).replace(microsecond=0).isoformat()


def _scope(value: Mapping[str, Any] | None) -> dict[str, list[Any]]:
    source = _mapping(value)
    return {key: _list(source.get(key)) for key in _SCOPE_KEYS}


def _proposal_scope(proposal: Mapping[str, Any]) -> dict[str, list[Any]]:
    return _scope(_mapping(proposal.get("proposal")))


def _safe_relative(value: Any) -> bool:
    text = _text(value).replace("\\", "/")
    if not text or Path(text).is_absolute():
        return False
    path = PurePosixPath(text)
    return not path.is_absolute() and ".." not in path.parts


def _subset(requested: Mapping[str, list[Any]], available: Mapping[str, list[Any]]) -> bool:
    for key in _SCOPE_KEYS:
        allowed = {_canonical(item) for item in available.get(key, [])}
        if any(_canonical(item) not in allowed for item in requested.get(key, [])):
            return False
    return True


def _security_invariants() -> dict[str, bool]:
    return {
        "execution_started": False, "mutation_started": False,
        "mutation_allowed": False, "patch_application_allowed": False,
        "autonomous_apply_allowed": False,
        "requires_controlled_executor": True,
        "requires_separate_apply_step": True,
    }


def _base(status: str, *, controlled: bool, validated_at: str) -> dict[str, Any]:
    invariants = _security_invariants()
    return {
        "schema": RUNTIME_CONTROLLED_APPLY_ADMISSION_SCHEMA,
        "ok": status == "admitted", "admission_status": status,
        "admission_id": "", "proposal_id": "", "approval_id": "",
        "apply_admitted": status == "admitted", "controlled": controlled,
        "scope": _scope({}), "proposal_fingerprint": "",
        "approval_proposal_fingerprint": "", "scope_fingerprint": "",
        "approval_scope_fingerprint": "", "validated_at": validated_at,
        "expires_at": None, "audit_record": {},
        **invariants, "repair_execution_allowed": False,
        "decision_authority": False, "requested_changes_modified": False,
    }


@dataclass(frozen=True)
class RuntimeControlledApplyAdmission:
    clock: Callable[[], Any] = _utc_now

    def admit(self, *, proposal: Mapping[str, Any],
              approval_record: Mapping[str, Any], controlled: bool,
              now: Any = None) -> dict[str, Any]:
        original_proposal = _mapping(proposal)
        approval = _mapping(approval_record)
        try:
            validated_at = _time_text(now if now is not None else self.clock())
        except (TypeError, ValueError):
            validated_at = ""
            return self._finish(_base("admission_error", controlled=controlled,
                                      validated_at=validated_at),
                                original_proposal, approval, "invalid_now")

        status, reason = self._validate(original_proposal, approval,
                                        controlled, validated_at)
        result = _base(status, controlled=controlled, validated_at=validated_at)
        result["proposal_id"] = _text(original_proposal.get("proposal_id"))
        result["approval_id"] = _text(approval.get("approval_id"))
        result["expires_at"] = approval.get("expires_at")
        result["scope"] = _scope(approval.get("approved_scope"))
        result["proposal_fingerprint"] = _fingerprint(original_proposal)
        result["approval_proposal_fingerprint"] = _text(approval.get("proposal_fingerprint"))
        result["scope_fingerprint"] = _fingerprint(result["scope"])
        result["approval_scope_fingerprint"] = _text(approval.get("scope_fingerprint"))
        return self._finish(result, original_proposal, approval, reason)

    def _validate(self, proposal: Mapping[str, Any], approval: Mapping[str, Any],
                  controlled: bool, validated_at: str) -> tuple[str, str]:
        if not controlled:
            return "denied_uncontrolled_mode", "controlled_mode_required"
        if proposal.get("schema") != _PROPOSAL_SCHEMA or not _text(proposal.get("proposal_id")):
            return "denied_invalid_proposal", "invalid_proposal"
        if proposal.get("proposal_status") not in {"proposal_created", "manual_review_required"}:
            return ("denied_safety_invariant_violation" if proposal.get("proposal_status") == "proposal_blocked_by_safety"
                    else "denied_invalid_proposal", "proposal_status_not_admissible")
        if (proposal.get("requires_operator_approval") is not True or
                proposal.get("mutation_allowed") is not False or
                proposal.get("autonomous_apply_allowed") is not False or
                proposal.get("patch_generation_allowed") is not False):
            return "denied_safety_invariant_violation", "proposal_security_boundary_invalid"
        proposal_scope = _proposal_scope(proposal)
        if any(not _safe_relative(path) for path in proposal_scope["target_files"]):
            return "denied_invalid_proposal", "proposal_target_path_invalid"
        if approval.get("schema") != _APPROVAL_SCHEMA or not _text(approval.get("approval_id")):
            return "denied_invalid_approval", "invalid_approval"
        if not _text(approval.get("operator_id")):
            return "denied_missing_operator_approval", "operator_id_required"
        if approval.get("revoked") is True or approval.get("approval_status") == "revoked":
            return "denied_revoked", "approval_revoked"
        if approval.get("expired") is True or approval.get("approval_status") == "expired":
            return "denied_expired", "approval_expired"
        if approval.get("approval_status") != "approved" or approval.get("decision") != "approve":
            return "denied_not_approved", "approval_not_approved"
        if (approval.get("execution_authority_granted") is not False or
                approval.get("mutation_allowed") is not False or
                approval.get("patch_application_allowed") is not False or
                approval.get("autonomous_apply_allowed") is not False or
                approval.get("requires_controlled_apply") is not True):
            return "denied_safety_invariant_violation", "approval_security_boundary_invalid"
        if _text(approval.get("proposal_id")) != _text(proposal.get("proposal_id")):
            return "denied_invalid_approval", "proposal_id_mismatch"
        if _text(approval.get("proposal_fingerprint")) != _fingerprint(proposal):
            return "denied_proposal_fingerprint_mismatch", "proposal_fingerprint_mismatch"
        approved_scope = _scope(approval.get("approved_scope"))
        if any(not _safe_relative(path) for path in approved_scope["target_files"]):
            return "denied_scope_outside_proposal", "approved_scope_path_invalid"
        if not _subset(approved_scope, proposal_scope):
            return "denied_scope_outside_proposal", "approved_scope_expands_proposal"
        if _text(approval.get("scope_fingerprint")) != _fingerprint(approved_scope):
            return "denied_scope_fingerprint_mismatch", "scope_fingerprint_mismatch"
        if approval.get("expires_at"):
            try:
                if _parse_time(validated_at) >= _parse_time(approval["expires_at"]):
                    return "denied_expired", "approval_expired"
            except (TypeError, ValueError):
                return "denied_invalid_approval", "invalid_expiration"
        return "admitted", ""

    def _finish(self, result: dict[str, Any], proposal: Mapping[str, Any],
                approval: Mapping[str, Any], reason: str) -> dict[str, Any]:
        seed = {key: result.get(key) for key in (
            "proposal_id", "approval_id", "proposal_fingerprint",
            "scope_fingerprint", "validated_at")}
        result["admission_id"] = f"apply-admission-{_fingerprint(seed)[:16]}"
        result["audit_record"] = {
            "event_type": "controlled_apply_admission_evaluated",
            "admission_id": result["admission_id"],
            "proposal_id": result["proposal_id"], "approval_id": result["approval_id"],
            "operator_id": _text(approval.get("operator_id")),
            "admission_status": result["admission_status"],
            "apply_admitted": result["apply_admitted"],
            "validated_at": result["validated_at"], "expires_at": result["expires_at"],
            "proposal_fingerprint": result["proposal_fingerprint"],
            "approval_proposal_fingerprint": result["approval_proposal_fingerprint"],
            "scope_fingerprint": result["scope_fingerprint"],
            "approval_scope_fingerprint": result["approval_scope_fingerprint"],
            "controlled": result["controlled"], "denial_reason": reason,
            "security_invariants": _security_invariants(),
        }
        return result


__all__ = ["RUNTIME_CONTROLLED_APPLY_ADMISSION_SCHEMA",
           "RuntimeControlledApplyAdmission"]

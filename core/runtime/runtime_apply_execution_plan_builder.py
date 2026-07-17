from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping


RUNTIME_APPLY_EXECUTION_PLAN_SCHEMA = "zero.runtime.apply_execution_plan.v1"
_PROPOSAL_SCHEMA = "zero.runtime.change_proposal_engine.v1"
_APPROVAL_SCHEMA = "zero.runtime.operator_approval_gate.v1"
_ADMISSION_SCHEMA = "zero.runtime.controlled_apply_admission.v1"
_SCOPE_KEYS = ("target_files", "recommended_actions", "validation_requirements",
               "rollback_requirements")
_REQUIRED_VALIDATIONS = ("confirm_expected_file_state",
                         "confirm_no_unapproved_paths_changed")


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


def _scope(value: Mapping[str, Any] | None) -> dict[str, list[Any]]:
    source = _mapping(value)
    return {key: _list(source.get(key)) for key in _SCOPE_KEYS}


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


def _unique_files(values: Any) -> list[str]:
    result: list[str] = []
    for value in _list(values):
        path = _text(value).replace("\\", "/")
        if path and path not in result:
            result.append(path)
    return result


def _validation_plan(requirements: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in requirements:
        requirement = _text(item.get("requirement")) if isinstance(item, Mapping) else _text(item)
        if not requirement or requirement in seen:
            continue
        seen.add(requirement)
        result.append({
            "validation_id": f"validation-{_fingerprint(requirement)[:16]}",
            "requirement": requirement, "required": True,
            "execution_allowed": False,
        })
    return result


def _rollback_flags(requirements: list[Any], allowed_files: list[str]) -> dict[str, bool]:
    names = {_text(item) for item in requirements if not isinstance(item, Mapping)}
    mappings = [item for item in requirements if isinstance(item, Mapping)]
    disabled = any(
        item.get(key) is False for item in mappings
        for key in ("rollback_plan_required", "rollback_evidence_required", "snapshot_required")
    )
    plan = any(item.get("rollback_plan_required") is True for item in mappings)
    evidence = (any(item.get("rollback_evidence_required") is True for item in mappings)
                or "rollback_evidence_required" in names)
    snapshot = (not allowed_files or "snapshot_target_files_before_change" in names
                or any(item.get("snapshot_required") is True for item in mappings))
    return {
        "rollback_required": bool(requirements) and plan and not disabled,
        "snapshot_required": snapshot,
        "rollback_evidence_required": evidence,
        "execution_allowed": False,
    }


def _security_invariants() -> dict[str, bool]:
    return {
        "execution_started": False, "mutation_started": False,
        "mutation_allowed": False, "patch_generation_allowed": False,
        "patch_application_allowed": False, "autonomous_apply_allowed": False,
        "requires_controlled_executor": True,
        "requires_separate_execution_step": True,
    }


def _constraints() -> dict[str, bool]:
    return {
        "controlled_mode_required": True, "allowed_files_only": True,
        "scope_expansion_allowed": False, "goal_mutation_allowed": False,
        "requested_changes_modification_allowed": False,
        "autonomous_task_creation_allowed": False,
        "patch_generation_allowed": False,
        "direct_filesystem_access_allowed": False,
        "governed_mutation_adapter_required": True, "validation_required": True,
        "rollback_required": True, "operator_approval_required": True,
        "admission_required": True,
    }


def _evidence_requirements() -> list[str]:
    return [
        "approval_audit_record_required", "admission_audit_record_required",
        "proposal_fingerprint_required", "pre_execution_snapshot_evidence_required",
        "post_execution_validation_evidence_required", "changed_files_evidence_required",
        "rollback_evidence_required",
    ]


def _base(status: str, built_at: str) -> dict[str, Any]:
    ready = status == "ready"
    return {
        "schema": RUNTIME_APPLY_EXECUTION_PLAN_SCHEMA, "ok": ready,
        "plan_status": status, "plan_id": "", "proposal_id": "",
        "approval_id": "", "admission_id": "", "plan_ready": ready,
        "controlled": False, "allowed_scope": _scope({}), "allowed_files": [],
        "validation_plan": [], "rollback_plan": {}, "evidence_requirements": [],
        "execution_constraints": _constraints(), "proposal_fingerprint": "",
        "approval_proposal_fingerprint": "", "scope_fingerprint": "",
        "approval_scope_fingerprint": "", "admission_scope_fingerprint": "",
        "built_at": built_at, "audit_record": {},
        **_security_invariants(), "decision_authority": False,
        "requested_changes_modified": False,
        "requires_post_execution_validation": True,
        "requires_rollback_capability": True,
    }


@dataclass(frozen=True)
class RuntimeApplyExecutionPlanBuilder:
    clock: Callable[[], Any] = _utc_now

    def build(self, *, proposal: Mapping[str, Any], approval_record: Mapping[str, Any],
              admission_record: Mapping[str, Any], now: Any = None) -> dict[str, Any]:
        proposal = _mapping(proposal)
        approval = _mapping(approval_record)
        admission = _mapping(admission_record)
        try:
            built_at = _time_text(now if now is not None else self.clock())
        except (TypeError, ValueError):
            return self._finish(_base("plan_error", ""), approval, "invalid_now")

        status, reason = self._validate(proposal, approval, admission, built_at)
        result = _base(status, built_at)
        allowed_scope = _scope(admission.get("scope"))
        allowed_files = _unique_files(allowed_scope["target_files"])
        result.update({
            "proposal_id": _text(proposal.get("proposal_id")),
            "approval_id": _text(approval.get("approval_id")),
            "admission_id": _text(admission.get("admission_id")),
            "controlled": admission.get("controlled") is True,
            "allowed_scope": allowed_scope, "allowed_files": allowed_files,
            "validation_plan": _validation_plan(allowed_scope["validation_requirements"]),
            "rollback_plan": _rollback_flags(allowed_scope["rollback_requirements"], allowed_files),
            "evidence_requirements": _evidence_requirements(),
            "proposal_fingerprint": _fingerprint(proposal),
            "approval_proposal_fingerprint": _text(approval.get("proposal_fingerprint")),
            "scope_fingerprint": _fingerprint(allowed_scope),
            "approval_scope_fingerprint": _text(approval.get("scope_fingerprint")),
            "admission_scope_fingerprint": _text(admission.get("scope_fingerprint")),
        })
        return self._finish(result, approval, reason)

    def _validate(self, p: Mapping[str, Any], a: Mapping[str, Any],
                  d: Mapping[str, Any], now: str) -> tuple[str, str]:
        if p.get("schema") != _PROPOSAL_SCHEMA or not _text(p.get("proposal_id")):
            return "denied_invalid_proposal", "invalid_proposal"
        if p.get("proposal_status") not in {"proposal_created", "manual_review_required"}:
            return "denied_invalid_proposal", "proposal_status_not_plannable"
        if (p.get("requires_operator_approval") is not True or p.get("mutation_allowed") is not False
                or p.get("patch_generation_allowed") is not False
                or p.get("autonomous_apply_allowed") is not False):
            return "denied_safety_invariant_violation", "proposal_security_boundary_invalid"
        proposal_scope = _scope(_mapping(p.get("proposal")))
        if any(not _safe_relative(path) for path in proposal_scope["target_files"]):
            return "denied_invalid_proposal", "proposal_target_path_invalid"
        if a.get("schema") != _APPROVAL_SCHEMA or not _text(a.get("approval_id")):
            return "denied_invalid_approval", "invalid_approval"
        if a.get("revoked") is True or a.get("approval_status") == "revoked":
            return "denied_revoked", "approval_revoked"
        if a.get("expired") is True or a.get("approval_status") == "expired":
            return "denied_expired", "approval_expired"
        if a.get("approval_status") != "approved" or a.get("decision") != "approve" or not _text(a.get("operator_id")):
            return "denied_invalid_approval", "approval_not_approved"
        if (a.get("execution_authority_granted") is not False or a.get("mutation_allowed") is not False
                or a.get("patch_application_allowed") is not False
                or a.get("autonomous_apply_allowed") is not False
                or a.get("requires_controlled_apply") is not True):
            return "denied_safety_invariant_violation", "approval_security_boundary_invalid"
        if d.get("schema") != _ADMISSION_SCHEMA or not _text(d.get("admission_id")):
            return "denied_invalid_admission", "invalid_admission"
        if d.get("admission_status") != "admitted" or d.get("apply_admitted") is not True:
            return "denied_not_admitted", "admission_not_admitted"
        if d.get("controlled") is not True:
            return "denied_uncontrolled", "controlled_admission_required"
        if (d.get("execution_started") is not False or d.get("mutation_started") is not False
                or d.get("mutation_allowed") is not False or d.get("patch_application_allowed") is not False
                or d.get("requires_controlled_executor") is not True
                or d.get("requires_separate_apply_step") is not True):
            return "denied_safety_invariant_violation", "admission_security_boundary_invalid"
        if _text(p.get("proposal_id")) != _text(a.get("proposal_id")) or _text(p.get("proposal_id")) != _text(d.get("proposal_id")):
            return "denied_proposal_mismatch", "proposal_id_mismatch"
        if _text(a.get("approval_id")) != _text(d.get("approval_id")):
            return "denied_approval_mismatch", "approval_id_mismatch"
        proposal_fp = _fingerprint(p)
        if (_text(a.get("proposal_fingerprint")) != proposal_fp
                or _text(d.get("proposal_fingerprint")) != proposal_fp
                or _text(d.get("approval_proposal_fingerprint")) != _text(a.get("proposal_fingerprint"))):
            return "denied_fingerprint_mismatch", "proposal_fingerprint_mismatch"
        approved_scope, admitted_scope = _scope(a.get("approved_scope")), _scope(d.get("scope"))
        if any(not _safe_relative(path) for path in admitted_scope["target_files"]):
            return "denied_scope_mismatch", "unsafe_admitted_path"
        if approved_scope != admitted_scope or not _subset(admitted_scope, proposal_scope):
            return "denied_scope_mismatch", "scope_mismatch"
        scope_fp = _fingerprint(approved_scope)
        if (_text(a.get("scope_fingerprint")) != scope_fp
                or _text(d.get("scope_fingerprint")) != scope_fp
                or _text(d.get("approval_scope_fingerprint")) != scope_fp):
            return "denied_fingerprint_mismatch", "scope_fingerprint_mismatch"
        if a.get("expires_at"):
            try:
                if _parse_time(now) >= _parse_time(a["expires_at"]):
                    return "denied_expired", "approval_expired"
            except (TypeError, ValueError):
                return "denied_invalid_approval", "invalid_expiration"
        requirements = admitted_scope["validation_requirements"]
        names = {_text(item.get("requirement")) if isinstance(item, Mapping) else _text(item) for item in requirements}
        if not requirements or any(item not in names for item in _REQUIRED_VALIDATIONS):
            return "denied_missing_validation_plan", "required_validation_missing"
        rollback = _rollback_flags(admitted_scope["rollback_requirements"], _unique_files(admitted_scope["target_files"]))
        if not all(rollback[key] for key in ("rollback_required", "snapshot_required", "rollback_evidence_required")):
            return "denied_missing_rollback_plan", "rollback_capability_missing"
        return "ready", ""

    def _finish(self, result: dict[str, Any], approval: Mapping[str, Any], reason: str) -> dict[str, Any]:
        seed = {key: result.get(key) for key in ("proposal_id", "approval_id", "admission_id",
                "allowed_scope", "proposal_fingerprint", "scope_fingerprint", "built_at")}
        result["plan_id"] = f"apply-plan-{_fingerprint(seed)[:16]}"
        rollback = _mapping(result.get("rollback_plan"))
        result["audit_record"] = {
            "event_type": "apply_execution_plan_built", "plan_id": result["plan_id"],
            "proposal_id": result["proposal_id"], "approval_id": result["approval_id"],
            "admission_id": result["admission_id"], "plan_status": result["plan_status"],
            "plan_ready": result["plan_ready"], "built_at": result["built_at"],
            "operator_id": _text(approval.get("operator_id")),
            "allowed_files_count": len(result["allowed_files"]),
            "validation_step_count": len(result["validation_plan"]),
            "rollback_required": rollback.get("rollback_required") is True,
            "proposal_fingerprint": result["proposal_fingerprint"],
            "scope_fingerprint": result["scope_fingerprint"],
            "denial_reason": reason, "security_invariants": _security_invariants(),
        }
        return result


def build_runtime_apply_execution_plan(**kwargs: Any) -> dict[str, Any]:
    return RuntimeApplyExecutionPlanBuilder().build(**kwargs)


__all__ = ["RUNTIME_APPLY_EXECUTION_PLAN_SCHEMA", "RuntimeApplyExecutionPlanBuilder",
           "build_runtime_apply_execution_plan"]

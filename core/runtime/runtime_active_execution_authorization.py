from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping


RUNTIME_ACTIVE_EXECUTION_AUTHORIZATION_CONTRACT = "zero.runtime.active_execution_authorization.v1"
RUNTIME_ACTIVE_AUTHORIZATION_REQUEST_CONTRACT = "zero.runtime.active_authorization_request.v1"
_ACTIVATION = "zero.runtime.controlled_execution_activation.v1"


def _text(value: Any) -> str: return str(value or "").strip()
def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _canonical(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fingerprint(value: Any) -> str: return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse(value: Any) -> datetime:
    if isinstance(value, datetime): result = value
    else:
        text = _text(value)
        if text.endswith("Z"): text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    if result.tzinfo is None: result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def authorize_active_execution(controlled_execution_result: Mapping[str, Any],
                               active_authorization: Mapping[str, Any], *,
                               now: Any = None) -> dict[str, Any]:
    activation, auth = _mapping(controlled_execution_result), _mapping(active_authorization)
    reasons: list[str] = []
    if activation.get("contract") != _ACTIVATION: reasons.append("invalid_controlled_execution_contract")
    if activation.get("activation_status") != "completed" or activation.get("dry_run_completed") is not True:
        reasons.append("controlled_dry_run_not_completed")
    fixed_false = ("active_execution_ready", "execution_allowed", "file_mutation_performed",
                   "patch_applied", "validation_executed", "rollback_executed", "commit_performed")
    if any(activation.get(key) is not False for key in fixed_false): reasons.append("unsafe_upstream_execution_state")
    token = _mapping(activation.get("token"))
    if token.get("token_status") != "issued": reasons.append("executor_token_not_issued")
    if activation.get("mode") != "controlled_dry_run" or token.get("mode") != "controlled_dry_run":
        reasons.append("invalid_upstream_mode")
    if auth.get("contract", auth.get("schema")) != RUNTIME_ACTIVE_AUTHORIZATION_REQUEST_CONTRACT:
        reasons.append("invalid_authorization_contract")
    for key in ("authorization_id", "controlled_execution_result_id", "token_id", "plan_id",
                "review_result_id", "operator_execution_request_id", "operator_id"):
        if not _text(auth.get(key)): reasons.append(f"{key}_required")
    decision = auth.get("decision")
    if not isinstance(decision, str) or decision not in {"authorized", "rejected"}: reasons.append("invalid_decision")
    if auth.get("authorized_mode") != "prepared_active_execution": reasons.append("invalid_authorized_mode")
    chain = {
        "controlled_execution_result_id": activation.get("activation_id"), "token_id": token.get("token_id"),
        "plan_id": activation.get("plan_id"), "review_result_id": activation.get("review_result_id"),
        "operator_execution_request_id": activation.get("operator_request_id"), "operator_id": token.get("operator_id")}
    for key, expected in chain.items():
        if _text(auth.get(key)) != _text(expected): reasons.append(f"{key}_mismatch")
    audit = _mapping(activation.get("audit_record"))
    if (_text(audit.get("activation_id")) != _text(activation.get("activation_id"))
            or _text(audit.get("token_id")) != _text(token.get("token_id"))): reasons.append("activation_audit_chain_mismatch")
    scope = token.get("allowed_files")
    if not isinstance(scope, list) or auth.get("acknowledged_scope") != scope: reasons.append("acknowledged_scope_mismatch")
    snapshot = _mapping(activation.get("snapshot_manifest")); validation = _mapping(activation.get("validation_evidence"))
    rollback = _mapping(activation.get("rollback_prepared_state")); dry_plan = _mapping(activation.get("dry_run_mutation_plan"))
    evidence = {
        "acknowledged_snapshot_manifest_id": snapshot.get("manifest_id"),
        "acknowledged_validation_evidence_id": validation.get("validation_evidence_id"),
        "acknowledged_rollback_state_id": rollback.get("rollback_state_id")}
    for key, expected in evidence.items():
        if not _text(expected) or _text(auth.get(key)) != _text(expected): reasons.append(f"{key}_mismatch")
    if not dry_plan.get("plan_id"): reasons.append("dry_run_mutation_plan_missing")
    if snapshot.get("all_paths_eligible") is not True or validation.get("preflight_validation_complete") is not True:
        reasons.append("dry_run_evidence_incomplete")
    for key in ("plan_fingerprint", "review_fingerprint", "scope_fingerprint"):
        value = _text(token.get(key))
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value): reasons.append(f"invalid_{key}")
    authorized_at = expires_at = current = token_expires = None
    for key, source in (("authorized_at", auth.get("authorized_at")), ("expires_at", auth.get("expires_at")),
                        ("now", now if now is not None else datetime.now(timezone.utc)),
                        ("token_expires_at", token.get("expires_at"))):
        try: parsed = _parse(source)
        except (TypeError, ValueError): reasons.append(f"invalid_{key}"); parsed = None
        if key == "authorized_at": authorized_at = parsed
        elif key == "expires_at": expires_at = parsed
        elif key == "now": current = parsed
        else: token_expires = parsed
    if authorized_at and expires_at:
        if expires_at <= authorized_at: reasons.append("invalid_authorization_expiration_order")
        if (expires_at - authorized_at).total_seconds() > 600: reasons.append("authorization_lifetime_exceeds_ten_minutes")
    if current and expires_at and current >= expires_at: reasons.append("authorization_expired")
    if current and token_expires and current >= token_expires: reasons.append("upstream_token_expired")
    if expires_at and token_expires and expires_at > token_expires: reasons.append("authorization_extends_upstream_authority")
    if decision == "authorized":
        if auth.get("acknowledged_no_automatic_commit") is not True: reasons.append("no_automatic_commit_not_acknowledged")
        if auth.get("acknowledged_manual_rollback_authority") is not True: reasons.append("manual_rollback_authority_not_acknowledged")
        if not isinstance(auth.get("acknowledged_risks"), list) or not auth.get("acknowledged_risks"):
            reasons.append("acknowledged_risks_required")
    valid, prepared = not reasons, not reasons and decision == "authorized"
    status = "authorized" if prepared else "rejected" if valid and decision == "rejected" else "invalid"
    seed = {"authorization_id": auth.get("authorization_id"), "activation_id": activation.get("activation_id"),
            "decision": decision, "authorized_at": auth.get("authorized_at"), "expires_at": auth.get("expires_at"),
            "scope": scope, "reasons": reasons}
    fixed = {"active_execution_ready": False, "execution_allowed": False,
             "file_mutation_allowed": False, "patch_application_allowed": False,
             "validation_execution_allowed": False, "rollback_execution_allowed": False,
             "commit_allowed": False}
    result = {"contract": RUNTIME_ACTIVE_EXECUTION_AUTHORIZATION_CONTRACT,
        "authorization_result_id": f"active-authorization-{_fingerprint(seed)[:16]}",
        "authorization_id": _text(auth.get("authorization_id")), "authorization_status": status,
        "authorization_valid": valid, "active_execution_prepared": prepared, **fixed,
        "plan_id": _text(activation.get("plan_id")), "review_result_id": _text(activation.get("review_result_id")),
        "token_id": _text(token.get("token_id")), "controlled_execution_result_id": _text(activation.get("activation_id")),
        "operator_id": _text(auth.get("operator_id")), "authorized_scope": deepcopy(scope) if isinstance(scope, list) else [],
        "authorized_at": _text(auth.get("authorized_at")), "expires_at": _text(auth.get("expires_at")),
        "required_next_boundary": "active_executor_invocation_gate",
        "prepared_execution_context": {"target_root_identity": token.get("target_root_identity", ""),
            "scope": deepcopy(scope) if isinstance(scope, list) else [],
            "snapshot_manifest_reference": snapshot.get("manifest_id", ""),
            "validation_evidence_reference": validation.get("validation_evidence_id", ""),
            "rollback_state_reference": rollback.get("rollback_state_id", ""),
            "mode": "prepared_active_execution"}, "reasons": reasons}
    result["audit_record"] = {"event_type": "active_execution_authorization_evaluated",
        "authorization_result_id": result["authorization_result_id"], "authorization_id": result["authorization_id"],
        "controlled_execution_result_id": result["controlled_execution_result_id"], "token_id": result["token_id"],
        "authorization_status": status, "active_execution_prepared": prepared, **fixed, "reasons": deepcopy(reasons)}
    return result


__all__ = ["RUNTIME_ACTIVE_AUTHORIZATION_REQUEST_CONTRACT",
           "RUNTIME_ACTIVE_EXECUTION_AUTHORIZATION_CONTRACT", "authorize_active_execution"]

from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Any, Mapping
from core.runtime.runtime_capability_activation_gate import AUTHORIZATION_CLASSES, AUTHORIZATION_REQUEST_SCHEMA, DECISION_SCHEMA, FUTURE_CONSUMERS, MODES, POLICY_SCHEMA, REQUEST_SCHEMA, REQUIRED_PROHIBITIONS, STATUSES, _hash

@dataclass(frozen=True)
class ActivationGateValidationResult:
    valid: bool
    errors: tuple[str, ...]

SENSITIVE = frozenset({"username", "hostname", "path", "absolute_path", "environment", "api_key", "token", "credential", "secret", "password", "exception", "traceback", "command", "callable", "provider", "detector", "module", "class"})
PREFIXES = {"policy_id": "capability-activation-gate-policy-", "request_id": "capability-activation-gate-request-", "decision_id": "capability-activation-gate-decision-", "authorization_request_id": "capability-activation-authorization-request-"}

def _result(errors: list[str]) -> ActivationGateValidationResult: return ActivationGateValidationResult(not errors, tuple(dict.fromkeys(errors)))
def _safe(value: Any) -> bool:
    try: json.dumps(value, allow_nan=False)
    except (TypeError, ValueError): return False
    def bad(v: Any) -> bool:
        if isinstance(v, Mapping): return any(str(k).casefold() in SENSITIVE or bad(x) for k, x in v.items())
        if isinstance(v, (list, tuple)): return any(bad(x) for x in v)
        return not isinstance(v, (str, int, float, bool, type(None))) or isinstance(v, str) and ("traceback (most recent" in v.casefold() or "object at 0x" in v.casefold())
    return not bad(value)
def _identity(value: Mapping[str, Any], key: str, excluded: frozenset[str] = frozenset()) -> bool:
    try:
        fp = _hash({k: v for k, v in value.items() if k not in excluded | {key, "fingerprint"}})
        return value.get("fingerprint") == fp and value.get(key) == PREFIXES[key] + fp[:24]
    except (TypeError, ValueError): return False

def validate_activation_gate_policy(value: Any) -> ActivationGateValidationResult:
    if not isinstance(value, Mapping): return _result(["policy_not_object"])
    e=[]
    if value.get("schema") != POLICY_SCHEMA: e.append("invalid_schema")
    if set(value.get("allowed_gate_modes", [])) != set(MODES) or not set(value.get("allowed_authorization_classes", [])) <= AUTHORIZATION_CLASSES or value.get("required_future_consumer") not in FUTURE_CONSUMERS: e.append("invalid_allowlist")
    if value.get("lease_requirement", {}).get("mutation_allowed") is not False or value.get("lease_requirement", {}).get("runtime_start_allowed") is not False or not REQUIRED_PROHIBITIONS <= set(value.get("prohibited_actions_requirement", [])): e.append("unsafe_policy")
    if not _identity(value, "policy_id") or not _safe(value): e.append("policy_identity_or_safety_invalid")
    return _result(e)

def validate_activation_gate_request(value: Any) -> ActivationGateValidationResult:
    if not isinstance(value, Mapping): return _result(["request_not_object"])
    e=[]; required={"schema","request_id","fingerprint","admission_decision_id","admission_decision_fingerprint","activation_handoff_id","activation_handoff_fingerprint","consumption_result_id","consumption_result_fingerprint","lease_id","lease_fingerprint","integration_id","integration_fingerprint","runtime_context_id","runtime_context_fingerprint","gate_mode","requested_authorization_class","requested_future_activation_consumer","policy","caller_metadata","requested_at"}
    e += [f"missing:{x}" for x in sorted(required-set(value))] + [f"unexpected:{x}" for x in sorted(set(value)-required)]
    if value.get("schema") != REQUEST_SCHEMA: e.append("invalid_schema")
    if value.get("gate_mode") not in MODES: e.append("unsupported_mode")
    if value.get("requested_authorization_class") not in AUTHORIZATION_CLASSES: e.append("unsupported_authorization_class")
    if value.get("requested_future_activation_consumer") not in FUTURE_CONSUMERS: e.append("unsupported_future_consumer")
    if not validate_activation_gate_policy(value.get("policy")).valid: e.append("invalid_policy")
    if not _identity(value, "request_id", frozenset({"requested_at"})): e.append("request_identity_mismatch")
    if not _safe({"caller_metadata": value.get("caller_metadata")}): e.append("unsafe_caller_metadata")
    return _result(e)

def validate_activation_gate_decision(value: Any) -> ActivationGateValidationResult:
    if not isinstance(value, Mapping): return _result(["decision_not_object"])
    e=[]
    if value.get("schema") != DECISION_SCHEMA or value.get("gate_status") not in STATUSES: e.append("invalid_decision")
    if value.get("allowed") is not (value.get("gate_status") == "allowed") or value.get("allowed") and value.get("blockers"): e.append("decision_state_mismatch")
    if any(value.get(k) is not False for k in ("runtime_started","mutation_performed","authorization_issued","token_issued","activation_performed")): e.append("unsafe_decision")
    if any(x != 0 for x in value.get("invocation_evidence", {}).values()): e.append("unsafe_invocation_evidence")
    auth=value.get("authorization_request")
    if auth is not None and not validate_activation_authorization_request(auth).valid: e.append("invalid_authorization_request")
    if not _identity(value, "decision_id", frozenset({"evaluated_at","authorization_request","authorization_request_linkage"})) or not _safe(value): e.append("decision_identity_or_safety_invalid")
    return _result(e)

def validate_activation_authorization_request(value: Any) -> ActivationGateValidationResult:
    if not isinstance(value, Mapping): return _result(["authorization_request_not_object"])
    e=[]
    if value.get("schema") != AUTHORIZATION_REQUEST_SCHEMA: e.append("invalid_schema")
    if value.get("requested_authorization_class") not in AUTHORIZATION_CLASSES or value.get("future_activation_consumer") not in FUTURE_CONSUMERS: e.append("invalid_allowlist")
    if value.get("requested_action") != "consider_capability_runtime_activation" or value.get("mutation_classification") != "none": e.append("unsafe_action")
    if any(value.get(k) is not False for k in ("runtime_start_requested","authorization_issued","token_issued","activation_performed")): e.append("unsafe_authorization_request")
    if not REQUIRED_PROHIBITIONS <= set(value.get("prohibited_actions", [])): e.append("missing_prohibition")
    if not _identity(value, "authorization_request_id", frozenset({"prepared_at","gate_decision_linkage"})) or not _safe(value): e.append("authorization_request_identity_or_safety_invalid")
    return _result(e)

__all__=["ActivationGateValidationResult","validate_activation_gate_policy","validate_activation_gate_request","validate_activation_gate_decision","validate_activation_authorization_request"]

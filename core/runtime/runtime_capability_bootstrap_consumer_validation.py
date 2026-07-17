from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_bootstrap_consumer import CONSUMER_ID, CONTEXT_VIEW_SCHEMA, DESCRIPTOR_SCHEMA, ELIGIBILITY_SCHEMA, LEASE_SCHEMA, MODES, POLICY_SCHEMA, PROHIBITED_ACTIONS, REQUEST_SCHEMA, RESULT_SCHEMA, SCOPES, STATUSES, _hash

@dataclass(frozen=True)
class ConsumerValidationResult:
    valid: bool
    errors: tuple[str, ...]

_SENSITIVE = frozenset({"username", "hostname", "home", "path", "absolute_path", "environment", "environment_values", "api_key", "token", "access_token", "credential", "credentials", "exception", "traceback", "command", "callable", "provider", "provider_instance", "detector", "module", "class"})
def _safe(value: Any) -> bool:
    try: json.dumps(value, allow_nan=False)
    except (TypeError, ValueError): return False
    def unsafe(item: Any) -> bool:
        if isinstance(item, Mapping): return any(str(k).casefold() in _SENSITIVE or unsafe(v) for k, v in item.items())
        if isinstance(item, (list, tuple)): return any(unsafe(v) for v in item)
        return not isinstance(item, (str, int, float, bool, type(None))) or (isinstance(item, str) and ("object at 0x" in item.casefold() or "traceback (most recent" in item.casefold()))
    return not unsafe(value)
def _identity(value: Mapping[str, Any], id_key: str | None, excluded: frozenset[str] = frozenset()) -> bool:
    try:
        identity = {k: v for k, v in value.items() if k not in excluded | {"fingerprint"} | ({id_key} if id_key else set())}
        fp = _hash(identity)
        return value.get("fingerprint") == fp and (id_key is None or value.get(id_key, "").endswith(fp[:24]))
    except (TypeError, ValueError): return False
def _result(errors: list[str]) -> ConsumerValidationResult: return ConsumerValidationResult(not errors, tuple(dict.fromkeys(errors)))

def validate_consumer_descriptor(value: Any) -> ConsumerValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return _result(["descriptor_not_object"])
    if value.get("schema") != DESCRIPTOR_SCHEMA or value.get("consumer_id") != CONSUMER_ID: errors.append("invalid_descriptor")
    if set(value.get("allowed_consumption_modes", [])) != MODES or set(value.get("allowed_lease_scopes", [])) != SCOPES: errors.append("invalid_allowlist")
    if value.get("read_only_required") is not True or value.get("mutation_classification") != "none": errors.append("unsafe_descriptor")
    if not _identity(value, None) or not _safe(value): errors.append("descriptor_identity_or_safety_invalid")
    return _result(errors)

def validate_consumption_request(value: Any) -> ConsumerValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return _result(["request_not_object"])
    required = {"schema", "request_id", "fingerprint", "integration_id", "integration_fingerprint", "runtime_context_id", "runtime_context_fingerprint", "consumer_id", "mode", "requested_lease_scope", "policy", "metadata", "requested_at", "lease_id"}
    errors += [f"missing:{x}" for x in sorted(required-set(value))] + [f"unexpected:{x}" for x in sorted(set(value)-required)]
    if value.get("schema") != REQUEST_SCHEMA: errors.append("invalid_schema")
    if value.get("consumer_id") != CONSUMER_ID: errors.append("wrong_consumer")
    if value.get("mode") not in MODES: errors.append("unsupported_mode")
    if value.get("requested_lease_scope") not in SCOPES: errors.append("unsupported_scope")
    policy = value.get("policy", {})
    if not isinstance(policy, Mapping) or policy.get("schema") != POLICY_SCHEMA or policy.get("read_only_required") is not True or policy.get("mutation_allowed") is not False or policy.get("runtime_start_allowed") is not False or not set(PROHIBITED_ACTIONS) <= set(policy.get("required_prohibited_actions", [])): errors.append("invalid_policy")
    elif policy.get("fingerprint") != _hash({k: v for k, v in policy.items() if k != "fingerprint"}): errors.append("policy_identity_mismatch")
    if not _identity(value, "request_id", frozenset({"requested_at"})): errors.append("request_identity_mismatch")
    if not _safe({"metadata": value.get("metadata")}): errors.append("unsafe_metadata")
    return _result(errors)

def validate_eligibility(value: Any) -> ConsumerValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return _result(["eligibility_not_object"])
    if value.get("schema") != ELIGIBILITY_SCHEMA or value.get("consumer_id") != CONSUMER_ID: errors.append("invalid_eligibility")
    if value.get("eligible") is not (value.get("status") == "eligible") or bool(value.get("reason_codes")) is value.get("eligible"): errors.append("eligibility_state_mismatch")
    if not _identity(value, None): errors.append("eligibility_identity_mismatch")
    return _result(errors)

def validate_lease(value: Any) -> ConsumerValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return _result(["lease_not_object"])
    if value.get("schema") != LEASE_SCHEMA or value.get("consumer_id") != CONSUMER_ID or value.get("lease_scope") not in SCOPES: errors.append("invalid_lease")
    if value.get("read_only") is not True or value.get("mutation_allowed") is not False or value.get("runtime_start_allowed") is not False: errors.append("unsafe_lease")
    if value.get("permissions") != ["read_detached_context"] or not set(PROHIBITED_ACTIONS) <= set(value.get("prohibited_actions", [])): errors.append("invalid_permissions")
    if value.get("lease_status") not in {"active", "revoked"} or (value.get("lease_status") == "revoked") != (value.get("revocation_status") == "revoked"): errors.append("lease_state_mismatch")
    if not _identity(value, "lease_id", frozenset({"issued_at", "expires_at", "lease_status", "revocation_status"})): errors.append("lease_identity_mismatch")
    if not _safe(value): errors.append("unsafe_lease_metadata")
    return _result(errors)

def validate_consumption_result(value: Any) -> ConsumerValidationResult:
    errors: list[str] = []
    if not isinstance(value, Mapping): return _result(["result_not_object"])
    if value.get("schema") != RESULT_SCHEMA or value.get("status") not in STATUSES: errors.append("invalid_result")
    if value.get("runtime_started") is not False or value.get("mutation_performed") is not False: errors.append("unsafe_result")
    if any(v != 0 for v in value.get("invocation_evidence", {}).values()): errors.append("unsafe_invocation_evidence")
    if not validate_eligibility(value.get("eligibility")).valid: errors.append("invalid_eligibility")
    lease = value.get("lease")
    if lease is not None and not validate_lease(lease).valid: errors.append("invalid_lease")
    view = value.get("read_only_context_view")
    if view is not None and (not isinstance(view, Mapping) or view.get("schema") != CONTEXT_VIEW_SCHEMA or not _safe(view)): errors.append("invalid_context_view")
    if value.get("status") == "consumed" and (view is None or lease is None): errors.append("incomplete_consumption")
    if not _identity(value, "consumption_id", frozenset({"consumed_at"})): errors.append("result_identity_mismatch")
    if not _safe(value): errors.append("unsafe_result_metadata")
    return _result(errors)

__all__ = ["ConsumerValidationResult", "validate_consumer_descriptor", "validate_consumption_request", "validate_eligibility", "validate_lease", "validate_consumption_result"]

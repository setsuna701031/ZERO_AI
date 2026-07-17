from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_detection import DETECTION_VERSION, DOMAINS, SCHEMA, STATUSES, compute_detection_fingerprint, compute_detection_id


REQUIRED = frozenset({"schema", "detection_version", "detection_id", "fingerprint", "observed_at", "detector_set_fingerprint", "requested_domains", "completed_domains", "overall_status", "results", "warnings", "source"})
_SENSITIVE = frozenset({"username", "hostname", "home", "environment", "environment_variables", "credential", "credentials", "token", "access_token", "api_key", "ip", "mac", "path", "executable", "exception", "traceback", "message"})


@dataclass(frozen=True)
class DetectionValidationResult:
    valid: bool
    errors: tuple[str, ...]


def validate_capability_detection(value: Any) -> DetectionValidationResult:
    if not isinstance(value, Mapping): return DetectionValidationResult(False, ("detection_not_object",))
    errors: list[str] = []
    missing = sorted(REQUIRED - set(value)); errors.extend(f"missing:{key}" for key in missing)
    errors.extend(f"unexpected:{key}" for key in sorted(set(value) - REQUIRED))
    if value.get("schema") != SCHEMA: errors.append("invalid_schema")
    if value.get("detection_version") != DETECTION_VERSION: errors.append("invalid_detection_version")
    requested, completed, results = value.get("requested_domains"), value.get("completed_domains"), value.get("results")
    if not isinstance(requested, list) or requested != sorted(set(requested)) or any(item not in DOMAINS for item in requested): errors.append("invalid_requested_domains")
    if not isinstance(completed, list) or completed != sorted(set(completed)) or any(item not in DOMAINS for item in completed): errors.append("invalid_completed_domains")
    domains: list[str] = []
    if not isinstance(results, list): errors.append("invalid_results")
    else:
        for index, result in enumerate(results):
            if not isinstance(result, Mapping): errors.append(f"invalid_result:{index}"); continue
            domain = result.get("domain"); domains.append(domain)
            if set(result) != {"detector_id", "domain", "status", "evidence", "error_code", "provider"}: errors.append(f"invalid_result_fields:{index}")
            if domain not in DOMAINS or result.get("status") not in STATUSES or not isinstance(result.get("detector_id"), str) or not isinstance(result.get("evidence"), Mapping) or not isinstance(result.get("provider"), Mapping): errors.append(f"invalid_result:{index}")
            elif result["provider"].get("detector_id") != result["detector_id"] or result["provider"].get("domain") != domain: errors.append(f"detector_linkage_mismatch:{index}")
        if len(domains) != len(set(domains)): errors.append("duplicate_domain")
        if domains != sorted(domains): errors.append("non_canonical_result_order")
    if isinstance(requested, list) and isinstance(completed, list) and (requested != completed or completed != domains): errors.append("domain_consistency_mismatch")
    if value.get("overall_status") not in {"available", "partial", "failed"}: errors.append("invalid_overall_status")
    if not isinstance(value.get("warnings"), list) or value.get("warnings") != sorted(set(value.get("warnings", []))): errors.append("invalid_warnings")
    def sensitive(item: Any) -> bool:
        if isinstance(item, Mapping): return any(str(key).casefold() in _SENSITIVE or sensitive(child) for key, child in item.items())
        if isinstance(item, list): return any(sensitive(child) for child in item)
        if not isinstance(item, (str, int, float, bool, type(None))): return True
        return isinstance(item, str) and ("object at 0x" in item.casefold() or "traceback (most recent" in item.casefold())
    if sensitive(value): errors.append("sensitive_or_unsafe_value")
    try: json.dumps(value, allow_nan=False)
    except (TypeError, ValueError): errors.append("not_json_serializable")
    if not missing:
        try:
            if value.get("fingerprint") != compute_detection_fingerprint(value): errors.append("fingerprint_mismatch")
            if value.get("detection_id") != compute_detection_id(value): errors.append("detection_id_mismatch")
        except (TypeError, ValueError): pass
    return DetectionValidationResult(not errors, tuple(errors))


__all__ = ["REQUIRED", "DetectionValidationResult", "validate_capability_detection"]

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_detection import DOMAINS
from core.runtime.runtime_capability_provider_discovery import DISCOVERY_SCHEMA, REJECTION_REASONS, _snapshot_fingerprint, _unsafe


@dataclass(frozen=True)
class DiscoveryValidationResult:
    valid: bool
    errors: tuple[str, ...]


def validate_capability_provider_discovery(value: Any) -> DiscoveryValidationResult:
    required = {"schema", "discovery_id", "fingerprint", "descriptor_set_fingerprint", "requested_domains", "platform_context", "compatibility_context", "selected_providers", "rejected_providers", "unresolved_domains", "conflicts", "warnings", "source_metadata", "observed_at"}
    if not isinstance(value, Mapping): return DiscoveryValidationResult(False, ("discovery_not_object",))
    errors = [f"missing:{key}" for key in sorted(required - set(value))] + [f"unexpected:{key}" for key in sorted(set(value) - required)]
    if value.get("schema") != DISCOVERY_SCHEMA: errors.append("invalid_schema")
    requested, unresolved = value.get("requested_domains"), value.get("unresolved_domains")
    if not isinstance(requested, list) or requested != sorted(set(requested)) or any(x not in DOMAINS for x in requested): errors.append("invalid_requested_domains")
    if not isinstance(unresolved, list) or unresolved != sorted(set(unresolved)): errors.append("invalid_unresolved_domains")
    selected, rejected = value.get("selected_providers"), value.get("rejected_providers")
    if not isinstance(selected, list) or selected != sorted(selected, key=lambda x: x.get("domain", "") if isinstance(x, Mapping) else ""): errors.append("invalid_selected_providers")
    if not isinstance(rejected, list) or any(not isinstance(x, Mapping) or set(x) != {"provider_id", "detector_id", "domain", "reason"} or x.get("reason") not in REJECTION_REASONS for x in rejected): errors.append("invalid_rejected_providers")
    elif rejected != sorted(rejected, key=lambda x: (x["domain"], x["provider_id"], x["detector_id"], x["reason"])): errors.append("non_canonical_rejected_order")
    if isinstance(selected, list) and isinstance(requested, list) and isinstance(unresolved, list):
        domains = [x.get("domain") for x in selected if isinstance(x, Mapping)]
        if len(domains) != len(set(domains)) or sorted(set(requested) - set(domains)) != unresolved: errors.append("domain_consistency_mismatch")
    try: json.dumps(value, allow_nan=False)
    except (TypeError, ValueError): errors.append("not_json_serializable")
    if _unsafe(value): errors.append("sensitive_or_unsafe_value")
    if not required - set(value):
        try:
            fingerprint = _snapshot_fingerprint(value)
            if value.get("fingerprint") != fingerprint: errors.append("fingerprint_mismatch")
            if value.get("discovery_id") != "capability-discovery-" + fingerprint[:24]: errors.append("discovery_id_mismatch")
        except (TypeError, ValueError): pass
    return DiscoveryValidationResult(not errors, tuple(errors))


__all__ = ["DiscoveryValidationResult", "validate_capability_provider_discovery"]

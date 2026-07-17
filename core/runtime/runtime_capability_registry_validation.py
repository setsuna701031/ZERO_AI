from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_registry import REGISTRY_VERSION, SCHEMA, RegistryError, compute_registry_fingerprint, compute_registry_id, normalize_entry


REQUIRED = frozenset({"schema", "registry_id", "fingerprint", "registry_version", "entries", "diagnostics"})
_SENSITIVE = frozenset({"username", "home", "credential", "credentials", "token", "ip", "mac", "traceback", "exception", "environment", "executable", "path"})


@dataclass(frozen=True)
class RegistryValidationResult:
    valid: bool
    errors: tuple[str, ...]


def validate_capability_registry(value: Any) -> RegistryValidationResult:
    if not isinstance(value, Mapping): return RegistryValidationResult(False, ("registry_not_object",))
    errors: list[str] = []
    missing = sorted(REQUIRED - set(value)); errors.extend(f"missing:{key}" for key in missing)
    errors.extend(f"unexpected:{key}" for key in sorted(set(value) - REQUIRED))
    if value.get("schema") != SCHEMA: errors.append("invalid_schema")
    if value.get("registry_version") != REGISTRY_VERSION: errors.append("invalid_registry_version")
    entries = value.get("entries")
    normalized: list[dict[str, Any]] = []
    if not isinstance(entries, list): errors.append("invalid_entries")
    else:
        for index, entry in enumerate(entries):
            try: normalized.append(normalize_entry(entry))
            except (RegistryError, TypeError): errors.append(f"invalid_entry:{index}")
        ids = [item["entry_id"] for item in normalized]
        semantic = [(item["kind"], item["capability_domain"], item["name"], item["provider_ref"]) for item in normalized]
        if len(ids) != len(set(ids)): errors.append("duplicate_entry_id")
        if len(semantic) != len(set(semantic)): errors.append("duplicate_semantic_key")
    diagnostics = value.get("diagnostics")
    if not isinstance(diagnostics, list) or len(diagnostics) > 100: errors.append("invalid_diagnostics")
    def sensitive(item: Any) -> bool:
        if isinstance(item, Mapping): return any(str(key).casefold() in _SENSITIVE or sensitive(child) for key, child in item.items())
        if isinstance(item, list): return any(sensitive(child) for child in item)
        return False
    if sensitive(value): errors.append("sensitive_field")
    try: json.dumps(value, allow_nan=False)
    except (TypeError, ValueError): errors.append("not_json_serializable")
    if not missing:
        try:
            if value.get("fingerprint") != compute_registry_fingerprint(value): errors.append("fingerprint_mismatch")
            if value.get("registry_id") != compute_registry_id(value): errors.append("registry_id_mismatch")
        except (TypeError, ValueError): pass
    return RegistryValidationResult(not errors, tuple(errors))


__all__ = ["REQUIRED", "RegistryValidationResult", "validate_capability_registry"]

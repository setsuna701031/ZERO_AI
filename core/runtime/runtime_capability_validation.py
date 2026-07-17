from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_profile import SCHEMA, compute_fingerprint, compute_profile_id


REQUIRED = {"schema", "profile_id", "fingerprint", "detected_at", "host", "operating_system", "python_runtime", "cpu", "memory", "storage", "accelerators", "network", "execution_environment", "available_tools", "installed_models", "power", "constraints", "diagnostics"}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...]


def validate_capability_profile(profile: Any) -> ValidationResult:
    errors: list[str] = []
    if not isinstance(profile, Mapping):
        return ValidationResult(False, ("profile_not_object",))
    missing = sorted(REQUIRED - set(profile))
    errors.extend(f"missing:{key}" for key in missing)
    if profile.get("schema") != SCHEMA: errors.append("invalid_schema")
    for section in ("host", "operating_system", "python_runtime", "cpu", "memory", "network", "execution_environment", "power"):
        if section in profile and not isinstance(profile[section], Mapping): errors.append(f"invalid_section:{section}")
    for section in ("storage", "accelerators", "available_tools", "installed_models", "constraints", "diagnostics"):
        if section in profile and not isinstance(profile[section], list): errors.append(f"invalid_section:{section}")
    for section, keys in (("memory", ("total_bytes", "available_bytes")),):
        value = profile.get(section, {})
        if isinstance(value, Mapping):
            for key in keys:
                if value.get(key) is not None and (not isinstance(value.get(key), int) or isinstance(value.get(key), bool) or value[key] < 0): errors.append(f"invalid_byte_count:{section}.{key}")
    cpu = profile.get("cpu", {})
    if isinstance(cpu, Mapping) and (not isinstance(cpu.get("logical_cores"), int) or isinstance(cpu.get("logical_cores"), bool) or cpu.get("logical_cores", -1) < 0): errors.append("invalid_logical_cores")
    for index, item in enumerate(profile.get("storage", []) if isinstance(profile.get("storage"), list) else []):
        if not isinstance(item, Mapping): errors.append(f"invalid_entry:storage:{index}"); continue
        for key in ("total_bytes", "free_bytes"):
            if item.get(key) is not None and (not isinstance(item.get(key), int) or isinstance(item.get(key), bool) or item[key] < 0): errors.append(f"invalid_byte_count:storage.{key}")
    for section, key in (("available_tools", "name"), ("accelerators", "name"), ("installed_models", "name")):
        values = profile.get(section, [])
        if isinstance(values, list):
            names = [str(v.get(key, "")) for v in values if isinstance(v, Mapping)]
            if len(names) != len(set(names)): errors.append(f"duplicate_entries:{section}")
    try: json.dumps(profile, allow_nan=False)
    except (TypeError, ValueError): errors.append("not_json_serializable")
    if not missing:
        try:
            if profile.get("fingerprint") != compute_fingerprint(profile): errors.append("fingerprint_mismatch")
            if profile.get("profile_id") != compute_profile_id(profile): errors.append("profile_id_mismatch")
        except (TypeError, ValueError):
            pass  # not_json_serializable already reports the bounded validation error.
    return ValidationResult(not errors, tuple(errors))


__all__ = ["REQUIRED", "ValidationResult", "validate_capability_profile"]

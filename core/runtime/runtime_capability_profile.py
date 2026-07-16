from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping


SCHEMA = "zero.runtime.capability_profile.v1"
_IDENTITY_EXCLUDED = frozenset({"detected_at", "profile_id", "fingerprint"})


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity_content(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in profile.items() if key not in _IDENTITY_EXCLUDED}


def compute_fingerprint(profile: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_identity_content(profile)).encode("utf-8")).hexdigest()


def compute_profile_id(profile: Mapping[str, Any]) -> str:
    return f"capability-profile-{compute_fingerprint(profile)[:24]}"


def _sort_entries(values: Any, fields: tuple[str, ...]) -> list[Any]:
    items = deepcopy(list(values or []))
    return sorted(items, key=lambda item: tuple(str(item.get(field) or "").casefold() for field in fields))


def normalize_profile(content: Mapping[str, Any], *, detected_at: str | None = None) -> dict[str, Any]:
    value = deepcopy(dict(content))
    value["schema"] = SCHEMA
    value["storage"] = _sort_entries(value.get("storage"), ("path",))
    value["accelerators"] = _sort_entries(value.get("accelerators"), ("kind", "vendor", "name", "backend"))
    value["available_tools"] = _sort_entries(value.get("available_tools"), ("name",))
    value["installed_models"] = _sort_entries(value.get("installed_models"), ("provider", "name", "path"))
    value["constraints"] = deepcopy(list(value.get("constraints") or []))
    value["diagnostics"] = deepcopy(list(value.get("diagnostics") or []))
    value["detected_at"] = detected_at or value.get("detected_at") or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    value["fingerprint"] = compute_fingerprint(value)
    value["profile_id"] = compute_profile_id(value)
    # Enforce JSON-only detached state at the ownership boundary.
    return json.loads(canonical_json(value))


@dataclass(frozen=True)
class RuntimeCapabilityProfile:
    _value: dict[str, Any]

    @classmethod
    def create(cls, content: Mapping[str, Any], *, detected_at: str | None = None) -> "RuntimeCapabilityProfile":
        return cls(normalize_profile(content, detected_at=detected_at))

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._value)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self._value, ensure_ascii=False, sort_keys=True, indent=indent, allow_nan=False)

    def __getitem__(self, key: str) -> Any:
        return deepcopy(self._value[key])


__all__ = ["SCHEMA", "RuntimeCapabilityProfile", "canonical_json", "compute_fingerprint", "compute_profile_id", "normalize_profile"]

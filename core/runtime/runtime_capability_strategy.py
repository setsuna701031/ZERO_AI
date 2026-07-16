from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


SCHEMA = "zero.runtime.capability_strategy.v1"
STRATEGY_VERSION = 1
MAX_WORKERS_HARD_CAP = 8
LOW_MEMORY_AVAILABLE_BYTES = 2 * 1024**3
LOW_STORAGE_FREE_BYTES = 5 * 1024**3
_IDENTITY_EXCLUDED = frozenset({"strategy_id", "fingerprint", "generated_at"})


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity_content(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(item) for key, item in value.items() if key not in _IDENTITY_EXCLUDED}


def compute_strategy_fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_identity_content(value)).encode("utf-8")).hexdigest()


def compute_strategy_id(value: Mapping[str, Any]) -> str:
    return f"capability-strategy-{compute_strategy_fingerprint(value)[:24]}"


def normalize_strategy(content: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(content))
    value["schema"] = SCHEMA
    value["strategy_version"] = STRATEGY_VERSION
    for key, fields in (
        ("tool_preferences", ("name",)),
        ("model_preferences", ("provider", "name")),
        ("constraints", ("code",)),
        ("reasons", ("code",)),
        ("diagnostics", ("code",)),
    ):
        value[key] = sorted(
            deepcopy(list(value.get(key) or [])),
            key=lambda item: tuple(str(item.get(field, "")).casefold() for field in fields),
        )
    value["fingerprint"] = compute_strategy_fingerprint(value)
    value["strategy_id"] = compute_strategy_id(value)
    return json.loads(canonical_json(value))


@dataclass(frozen=True)
class RuntimeCapabilityStrategy:
    _value: dict[str, Any]

    @classmethod
    def create(cls, content: Mapping[str, Any]) -> "RuntimeCapabilityStrategy":
        return cls(normalize_strategy(content))

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._value)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self._value, ensure_ascii=False, sort_keys=True, indent=indent, allow_nan=False)

    def __getitem__(self, key: str) -> Any:
        return deepcopy(self._value[key])


__all__ = ["SCHEMA", "STRATEGY_VERSION", "MAX_WORKERS_HARD_CAP", "LOW_MEMORY_AVAILABLE_BYTES", "LOW_STORAGE_FREE_BYTES", "RuntimeCapabilityStrategy", "canonical_json", "compute_strategy_fingerprint", "compute_strategy_id", "normalize_strategy"]

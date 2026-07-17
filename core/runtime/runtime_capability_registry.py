from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping


SCHEMA = "zero.runtime.capability_registry.v1"
REGISTRY_VERSION = 1
MIN_PRIORITY = 0
MAX_PRIORITY = 1000
ALLOWED_KINDS = frozenset({"detector", "strategy_provider", "profile_enricher", "validator", "formatter"})
_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_.]*$")
_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class RegistryError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _entry_sort_key(entry: Mapping[str, Any]) -> tuple[Any, ...]:
    return (entry["kind"], entry["capability_domain"], -entry["priority"], entry["name"], entry["provider_ref"], entry["entry_id"])


def _semantic(entry: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return tuple(entry[key] for key in ("kind", "capability_domain", "name", "provider_ref"))  # type: ignore[return-value]


def compute_entry_id(entry: Mapping[str, Any]) -> str:
    content = {key: deepcopy(entry[key]) for key in ("name", "kind", "capability_domain", "provider_type", "provider_ref", "priority", "enabled", "metadata")}
    return "capability-entry-" + hashlib.sha256(_canonical(content).encode("utf-8")).hexdigest()[:24]


def _identity(entries: list[dict[str, Any]], diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": SCHEMA, "registry_version": REGISTRY_VERSION, "entries": entries, "diagnostics": diagnostics}


def compute_registry_fingerprint(snapshot: Mapping[str, Any]) -> str:
    content = {key: deepcopy(snapshot.get(key)) for key in ("schema", "registry_version", "entries", "diagnostics")}
    return hashlib.sha256(_canonical(content).encode("utf-8")).hexdigest()


def compute_registry_id(snapshot: Mapping[str, Any]) -> str:
    return "capability-registry-" + compute_registry_fingerprint(snapshot)[:24]


def normalize_entry(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"entry_id", "name", "kind", "capability_domain", "provider_type", "provider_ref", "priority", "enabled", "metadata"}
    if not isinstance(value, Mapping) or set(value) - allowed:
        raise RegistryError("invalid_entry_fields")
    entry = {key: deepcopy(value.get(key)) for key in allowed - {"entry_id"}}
    if not isinstance(entry["name"], str) or not _NAME.fullmatch(entry["name"]): raise RegistryError("invalid_name")
    if entry["kind"] not in ALLOWED_KINDS: raise RegistryError("invalid_kind")
    if not isinstance(entry["capability_domain"], str) or not _NAME.fullmatch(entry["capability_domain"]): raise RegistryError("invalid_capability_domain")
    if not isinstance(entry["provider_type"], str) or not _NAME.fullmatch(entry["provider_type"]): raise RegistryError("invalid_provider_type")
    if not isinstance(entry["provider_ref"], str) or not _SYMBOL.fullmatch(entry["provider_ref"]): raise RegistryError("invalid_provider_ref")
    if isinstance(entry["priority"], bool) or not isinstance(entry["priority"], int) or not MIN_PRIORITY <= entry["priority"] <= MAX_PRIORITY: raise RegistryError("invalid_priority")
    if not isinstance(entry["enabled"], bool): raise RegistryError("invalid_enabled")
    if not isinstance(entry["metadata"], Mapping): raise RegistryError("invalid_metadata")
    try: entry["metadata"] = json.loads(_canonical(entry["metadata"]))
    except (TypeError, ValueError): raise RegistryError("invalid_metadata") from None
    entry["entry_id"] = compute_entry_id(entry)
    if value.get("entry_id") is not None and value.get("entry_id") != entry["entry_id"]: raise RegistryError("entry_id_mismatch")
    return entry


@dataclass(frozen=True)
class RegistryResolution:
    entry: dict[str, Any]
    provider: Any = None


class RuntimeCapabilityRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        self._providers: dict[str, Any] = {}

    def register(self, entry: Mapping[str, Any], provider: Any = None) -> dict[str, Any]:
        normalized = normalize_entry(entry)
        existing = self._entries.get(normalized["entry_id"])
        if existing is not None:
            if existing != normalized: raise RegistryError("duplicate_entry_id")
            if provider is not None: self._providers[normalized["entry_id"]] = provider
            return deepcopy(existing)
        if any(_semantic(item) == _semantic(normalized) for item in self._entries.values()): raise RegistryError("duplicate_semantic_key")
        self._entries[normalized["entry_id"]] = deepcopy(normalized)
        if provider is not None: self._providers[normalized["entry_id"]] = provider
        return deepcopy(normalized)

    def unregister(self, entry_id: str) -> bool:
        removed = self._entries.pop(entry_id, None) is not None
        self._providers.pop(entry_id, None)
        return removed

    def get(self, entry_id: str) -> dict[str, Any] | None:
        value = self._entries.get(entry_id)
        return deepcopy(value) if value is not None else None

    def list_entries(self, kind: str | None = None, capability_domain: str | None = None, enabled_only: bool = False) -> list[dict[str, Any]]:
        values = [item for item in self._entries.values() if (kind is None or item["kind"] == kind) and (capability_domain is None or item["capability_domain"] == capability_domain) and (not enabled_only or item["enabled"])]
        return deepcopy(sorted(values, key=_entry_sort_key))

    def resolve(self, kind: str, capability_domain: str) -> RegistryResolution | None:
        values = self.list_entries(kind, capability_domain, enabled_only=True)
        if not values: return None
        entry = values[0]
        return RegistryResolution(entry, self._providers.get(entry["entry_id"]))

    def snapshot(self) -> dict[str, Any]:
        entries = self.list_entries()
        base = _identity(entries, [])
        fingerprint = compute_registry_fingerprint(base)
        return json.loads(_canonical({**base, "registry_id": "capability-registry-" + fingerprint[:24], "fingerprint": fingerprint}))


def _entry(name: str, kind: str, domain: str, provider_type: str, provider_ref: str, priority: int = 100) -> dict[str, Any]:
    return {"name": name, "kind": kind, "capability_domain": domain, "provider_type": provider_type, "provider_ref": provider_ref, "priority": priority, "enabled": True, "metadata": {}}


def build_default_capability_registry() -> RuntimeCapabilityRegistry:
    registry = RuntimeCapabilityRegistry()
    module = "core.runtime.runtime_capability_adapters"
    for name, domain, symbol in (("default_os_detector", "os", "OSAdapter"), ("default_cpu_detector", "cpu", "CPUAdapter"), ("default_memory_detector", "memory", "MemoryAdapter"), ("default_storage_detector", "storage", "StorageAdapter"), ("default_accelerator_detector", "accelerator", "AcceleratorAdapter"), ("default_tool_detector", "tool", "ToolAdapter"), ("default_model_detector", "model", "ModelAdapter"), ("default_execution_environment_detector", "execution_environment", "ExecutionEnvironmentAdapter"), ("default_power_detector", "power", "PowerAdapter")):
        registry.register(_entry(name, "detector", domain, "adapter", f"{module}:{symbol}"))
    registry.register(_entry("default_capability_strategy_provider", "strategy_provider", "capability", "selector", "core.runtime.runtime_capability_strategy_selector:select_capability_strategy"))
    return registry


__all__ = ["SCHEMA", "REGISTRY_VERSION", "MIN_PRIORITY", "MAX_PRIORITY", "ALLOWED_KINDS", "RegistryError", "RegistryResolution", "RuntimeCapabilityRegistry", "normalize_entry", "compute_entry_id", "compute_registry_fingerprint", "compute_registry_id", "build_default_capability_registry"]

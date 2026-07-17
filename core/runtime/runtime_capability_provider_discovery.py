from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import platform
import re
import sys
from typing import Any, Iterable, Mapping

from core.runtime.runtime_capability_detection import DOMAINS, DetectionContext, default_detector_providers


DESCRIPTOR_SCHEMA = "zero.runtime.capability_provider_descriptor.v1"
DISCOVERY_SCHEMA = "zero.runtime.capability_provider_discovery.v1"
CONTRACT_VERSION = 1
MIN_PRIORITY, MAX_PRIORITY = 0, 1000
REJECTION_REASONS = frozenset({"unsupported_platform", "unsupported_architecture", "unsupported_python", "disabled", "duplicate_provider_id", "duplicate_detector_id", "schema_incompatible", "lower_priority", "conflict", "malformed_descriptor"})
_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_DESCRIPTOR_FIELDS = frozenset({"schema", "provider_id", "detector_id", "domain", "provider_version", "contract_version", "priority", "supported_platform_families", "supported_architectures", "supported_python_versions", "implementation_kind", "source_kind", "enabled", "default", "metadata", "fingerprint"})
_SENSITIVE = frozenset({"username", "hostname", "home", "home_path", "environment", "environment_variables", "token", "access_token", "api_key", "credential", "credentials", "exception", "traceback", "callable", "class", "module", "path", "executable"})


class DiscoveryError(ValueError):
    def __init__(self, code: str) -> None: super().__init__(code); self.code = code


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _unsafe(value: Any) -> bool:
    if isinstance(value, Mapping): return any(str(key).casefold() in _SENSITIVE or _unsafe(child) for key, child in value.items())
    if isinstance(value, (list, tuple)): return any(_unsafe(child) for child in value)
    if not isinstance(value, (str, int, float, bool, type(None))): return True
    return isinstance(value, str) and ("object at 0x" in value.casefold() or "traceback (most recent" in value.casefold() or re.match(r"^[a-zA-Z]:[\\/]", value) is not None or value.startswith("/"))


def compute_descriptor_fingerprint(value: Mapping[str, Any]) -> str:
    content = {key: deepcopy(item) for key, item in value.items() if key != "fingerprint"}
    return hashlib.sha256(canonical_json(content).encode()).hexdigest()


def normalize_descriptor(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) - _DESCRIPTOR_FIELDS: raise DiscoveryError("malformed_descriptor")
    item = deepcopy(dict(value)); item.setdefault("schema", DESCRIPTOR_SCHEMA); item.setdefault("contract_version", CONTRACT_VERSION); item.setdefault("enabled", True); item.setdefault("default", False); item.setdefault("metadata", {})
    item.setdefault("supported_platform_families", ["any"]); item.setdefault("supported_architectures", ["any"]); item.setdefault("supported_python_versions", ["any"])
    if item["schema"] != DESCRIPTOR_SCHEMA or item["contract_version"] != CONTRACT_VERSION: raise DiscoveryError("schema_incompatible")
    if any(not isinstance(item.get(key), str) or not _ID.fullmatch(item[key]) for key in ("provider_id", "detector_id")): raise DiscoveryError("malformed_descriptor")
    if item.get("domain") not in DOMAINS or isinstance(item.get("priority"), bool) or not isinstance(item.get("priority"), int) or not MIN_PRIORITY <= item["priority"] <= MAX_PRIORITY: raise DiscoveryError("malformed_descriptor")
    if not isinstance(item.get("provider_version"), str) or not item["provider_version"] or item.get("implementation_kind") not in {"builtin", "process_local"} or item.get("source_kind") not in {"builtin", "explicit"}: raise DiscoveryError("malformed_descriptor")
    if not isinstance(item.get("enabled"), bool) or not isinstance(item.get("default"), bool) or not isinstance(item.get("metadata"), Mapping): raise DiscoveryError("malformed_descriptor")
    for key in ("supported_platform_families", "supported_architectures", "supported_python_versions"):
        values = item.get(key)
        if not isinstance(values, (list, tuple)) or not values or any(not isinstance(entry, str) or not entry for entry in values): raise DiscoveryError("malformed_descriptor")
        item[key] = sorted(set(entry.casefold() for entry in values))
    if _unsafe(item["metadata"]): raise DiscoveryError("malformed_descriptor")
    try: item["metadata"] = json.loads(canonical_json(item["metadata"]))
    except (TypeError, ValueError): raise DiscoveryError("malformed_descriptor") from None
    supplied = item.pop("fingerprint", None); item["fingerprint"] = compute_descriptor_fingerprint(item)
    if supplied is not None and supplied != item["fingerprint"]: raise DiscoveryError("malformed_descriptor")
    return json.loads(canonical_json(item))


def safe_platform_context(*, platform_family: str | None = None, architecture: str | None = None, python_version: str | None = None, python_implementation: str | None = None, execution_environment: str | None = None) -> dict[str, str]:
    family = (platform_family or platform.system() or "unknown").casefold(); arch = (architecture or platform.machine() or "unknown").casefold()
    version = python_version or f"{sys.version_info.major}.{sys.version_info.minor}"
    environment = execution_environment or ("windows_native" if family == "windows" else "linux_native" if family == "linux" else "unknown")
    return {"platform_family": family, "architecture": arch, "python_implementation": (python_implementation or platform.python_implementation() or "unknown").casefold(), "python_version": version, "execution_environment": environment.casefold()}


def builtin_provider_descriptors() -> list[dict[str, Any]]:
    return [normalize_descriptor({"provider_id": f"zero.{provider.detector_id}", "detector_id": provider.detector_id, "domain": provider.domain, "provider_version": "1", "priority": provider.priority, "supported_platform_families": list(provider.supported_platforms), "supported_architectures": ["any"], "supported_python_versions": ["any"], "implementation_kind": "builtin", "source_kind": "builtin", "enabled": True, "default": True, "metadata": {}}) for provider in default_detector_providers()]


def _compatible(item: Mapping[str, Any], context: Mapping[str, str]) -> str | None:
    if "any" not in item["supported_platform_families"] and context["platform_family"] not in item["supported_platform_families"]: return "unsupported_platform"
    if "any" not in item["supported_architectures"] and context["architecture"] not in item["supported_architectures"]: return "unsupported_architecture"
    if "any" not in item["supported_python_versions"] and context["python_version"] not in item["supported_python_versions"]: return "unsupported_python"
    return None


def _snapshot_fingerprint(value: Mapping[str, Any]) -> str:
    content = {key: deepcopy(item) for key, item in value.items() if key not in {"fingerprint", "discovery_id", "observed_at"}}
    content["selected_providers"] = [{key: child for key, child in item.items() if key != "binding_status"} for item in content.get("selected_providers", [])]
    return hashlib.sha256(canonical_json(content).encode()).hexdigest()


class ProcessLocalProviderBindings:
    def __init__(self) -> None: self._values: dict[str, Any] = {}
    def register(self, provider_id: str, provider: Any) -> None:
        if not _ID.fullmatch(provider_id) or provider is None: raise DiscoveryError("invalid_binding")
        self._values[provider_id] = provider
    def unregister(self, provider_id: str) -> bool: return self._values.pop(provider_id, None) is not None
    def resolve(self, provider_id: str) -> Any: return self._values.get(provider_id)
    def snapshot_metadata(self) -> list[dict[str, Any]]: return [{"provider_id": key, "bound": True} for key in sorted(self._values)]


def discover_providers(descriptors: Iterable[Mapping[str, Any]], *, domains: Iterable[str] | None = None, context: Mapping[str, str] | None = None, bindings: ProcessLocalProviderBindings | None = None, observed_at: str | None = None) -> dict[str, Any]:
    requested = sorted(set(domains if domains is not None else DOMAINS))
    if not requested or any(domain not in DOMAINS for domain in requested): raise DiscoveryError("invalid_requested_domain")
    normalized_context = safe_platform_context(**dict(context or {}))
    valid, rejected, conflicts = [], [], []
    for raw in descriptors:
        try: valid.append(normalize_descriptor(raw))
        except DiscoveryError as exc:
            def safe_symbol(key: str, fallback: str) -> str:
                candidate = raw.get(key) if isinstance(raw, Mapping) else None
                return candidate if isinstance(candidate, str) and _ID.fullmatch(candidate) else fallback
            domain = raw.get("domain") if isinstance(raw, Mapping) else None
            rejected.append({"provider_id": safe_symbol("provider_id", "invalid"), "detector_id": safe_symbol("detector_id", "invalid"), "domain": domain if domain in DOMAINS else "unknown", "reason": exc.code if exc.code in REJECTION_REASONS else "malformed_descriptor"})
    valid.sort(key=lambda x: (x["provider_id"], x["fingerprint"]))
    deduped: list[dict[str, Any]] = []
    for provider_id in sorted({item["provider_id"] for item in valid}):
        group = [item for item in valid if item["provider_id"] == provider_id]
        if len({item["fingerprint"] for item in group}) > 1:
            conflicts.append({"kind": "duplicate_provider_id", "provider_id": provider_id}); rejected.extend({"provider_id": x["provider_id"], "detector_id": x["detector_id"], "domain": x["domain"], "reason": "conflict"} for x in group)
        else: deduped.append(group[0])
    conflicted_detectors = {key for key in {x["detector_id"] for x in deduped} if len({x["provider_id"] for x in deduped if x["detector_id"] == key}) > 1}
    for detector_id in sorted(conflicted_detectors): conflicts.append({"kind": "duplicate_detector_id", "detector_id": detector_id})
    candidates = []
    for item in deduped:
        reason = "disabled" if not item["enabled"] else "duplicate_detector_id" if item["detector_id"] in conflicted_detectors else _compatible(item, normalized_context)
        if item["domain"] not in requested: continue
        if reason: rejected.append({"provider_id": item["provider_id"], "detector_id": item["detector_id"], "domain": item["domain"], "reason": reason})
        else: candidates.append(item)
    selected = []
    for domain in requested:
        choices = sorted((x for x in candidates if x["domain"] == domain), key=lambda x: (-x["priority"], x["provider_id"]))
        if choices:
            winner = choices[0]; bound = bindings is not None and bindings.resolve(winner["provider_id"]) is not None
            selected.append({"provider_id": winner["provider_id"], "detector_id": winner["detector_id"], "domain": domain, "priority": winner["priority"], "provider_version": winner["provider_version"], "descriptor_fingerprint": winner["fingerprint"], "compatibility": "compatible", "selection_reason": "highest_priority_then_provider_id", "binding_status": "bound" if bound else "unbound"})
            rejected.extend({"provider_id": x["provider_id"], "detector_id": x["detector_id"], "domain": domain, "reason": "lower_priority"} for x in choices[1:])
    selected.sort(key=lambda x: x["domain"]); rejected.sort(key=lambda x: (x["domain"], x["provider_id"], x["detector_id"], x["reason"])); conflicts.sort(key=canonical_json)
    descriptor_fingerprints = sorted(x["fingerprint"] for x in valid)
    descriptor_set_fingerprint = hashlib.sha256(canonical_json(descriptor_fingerprints).encode()).hexdigest()
    resolved = {x["domain"] for x in selected}
    base = {"schema": DISCOVERY_SCHEMA, "descriptor_set_fingerprint": descriptor_set_fingerprint, "requested_domains": requested, "platform_context": normalized_context, "compatibility_context": {"contract_version": CONTRACT_VERSION}, "selected_providers": selected, "rejected_providers": rejected, "unresolved_domains": sorted(set(requested) - resolved), "conflicts": conflicts, "warnings": sorted({x["reason"] for x in rejected}), "source_metadata": {"kind": "explicit_or_builtin_allowlist"}, "observed_at": observed_at}
    fingerprint = _snapshot_fingerprint(base)
    return json.loads(canonical_json({**base, "fingerprint": fingerprint, "discovery_id": "capability-discovery-" + fingerprint[:24]}))


@dataclass(frozen=True)
class DetectionProviderPlan:
    providers: tuple[Any, ...]
    unbound_selections: tuple[dict[str, Any], ...]
    discovery_id: str
    discovery_fingerprint: str


def discovery_to_detection_plan(snapshot: Mapping[str, Any], bindings: ProcessLocalProviderBindings) -> DetectionProviderPlan:
    """Build inert Detection input; missing bindings remain symbolic and are never repaired."""
    providers, unbound = [], []
    for item in snapshot.get("selected_providers", []):
        provider = bindings.resolve(item["provider_id"])
        if provider is None: unbound.append(deepcopy(dict(item)))
        else: providers.append(provider)
    return DetectionProviderPlan(tuple(providers), tuple(unbound), str(snapshot.get("discovery_id", "")), str(snapshot.get("fingerprint", "")))


__all__ = ["DESCRIPTOR_SCHEMA", "DISCOVERY_SCHEMA", "CONTRACT_VERSION", "REJECTION_REASONS", "DiscoveryError", "ProcessLocalProviderBindings", "DetectionProviderPlan", "canonical_json", "compute_descriptor_fingerprint", "normalize_descriptor", "safe_platform_context", "builtin_provider_descriptors", "discover_providers", "discovery_to_detection_plan"]

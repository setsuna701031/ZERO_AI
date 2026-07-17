from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
from typing import Any, Iterable, Mapping, Protocol


SCHEMA = "zero.runtime.capability_detection.v1"
DETECTION_VERSION = 1
PROVIDER_SCHEMA = "zero.runtime.capability_detector_provider.v1"
PROVIDER_VERSION = 1
DOMAINS = frozenset({"cpu", "accelerator", "memory", "storage", "network", "power", "operating_system", "execution_environment", "tools", "models"})
STATUSES = frozenset({"available", "partial", "unavailable", "unsupported", "failed"})
_IDENTITY_EXCLUDED = frozenset({"detection_id", "fingerprint", "observed_at"})


class DetectorProvider(Protocol):
    detector_id: str
    domain: str
    priority: int
    supported_platforms: tuple[str, ...]
    def detect(self, context: "DetectionContext") -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class DetectionContext:
    workspace_root: Path | None = None
    tool_allowlist: tuple[str, ...] = ("python", "git", "pytest")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def provider_metadata(provider: DetectorProvider) -> dict[str, Any]:
    return {"schema": PROVIDER_SCHEMA, "provider_version": PROVIDER_VERSION, "detector_id": provider.detector_id, "domain": provider.domain, "priority": provider.priority, "supported_platforms": sorted(provider.supported_platforms)}


def _provider_sort(provider: DetectorProvider) -> tuple[Any, ...]:
    return (provider.domain, -provider.priority, provider.detector_id)


def compute_detector_set_fingerprint(metadata: Iterable[Mapping[str, Any]]) -> str:
    values = sorted((deepcopy(dict(item)) for item in metadata), key=lambda item: (item["domain"], -item["priority"], item["detector_id"]))
    return hashlib.sha256(canonical_json(values).encode("utf-8")).hexdigest()


def _identity(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(item) for key, item in value.items() if key not in _IDENTITY_EXCLUDED}


def compute_detection_fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_identity(value)).encode("utf-8")).hexdigest()


def compute_detection_id(value: Mapping[str, Any]) -> str:
    return "capability-detection-" + compute_detection_fingerprint(value)[:24]


def _result(provider: DetectorProvider, status: str, evidence: Mapping[str, Any] | None = None, error_code: str | None = None) -> dict[str, Any]:
    return {"detector_id": provider.detector_id, "domain": provider.domain, "status": status, "evidence": deepcopy(dict(evidence or {})), "error_code": error_code, "provider": provider_metadata(provider)}


class BaseDetector:
    priority = 100
    supported_platforms = ("any",)


class OperatingSystemDetector(BaseDetector):
    detector_id, domain = "builtin_operating_system_v1", "operating_system"
    def detect(self, context: DetectionContext) -> Mapping[str, Any]:
        system = (platform.system() or "unknown").casefold()
        release = (platform.release() or "").casefold()
        environment = "wsl" if system == "linux" and "microsoft" in release else "windows_native" if system == "windows" else "linux_native" if system == "linux" else "unknown"
        return _result(self, "available", {"platform_family": system, "operating_system": system, "architecture": (platform.machine() or "unknown").casefold(), "python_implementation": platform.python_implementation().casefold(), "python_version": [sys.version_info.major, sys.version_info.minor], "execution_environment": environment})


class CpuDetector(BaseDetector):
    detector_id, domain = "builtin_cpu_v1", "cpu"
    def detect(self, context: DetectionContext) -> Mapping[str, Any]:
        cores = os.cpu_count()
        return _result(self, "available" if cores is not None else "unavailable", {"logical_cores": cores, "architecture": (platform.machine() or "unknown").casefold()}, None if cores is not None else "cpu_count_unavailable")


class MemoryDetector(BaseDetector):
    detector_id, domain = "builtin_memory_v1", "memory"
    def detect(self, context: DetectionContext) -> Mapping[str, Any]:
        total = None
        if sys.platform == "win32":
            try:
                import ctypes
                class MemoryStatus(ctypes.Structure):
                    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong), ("page_total", ctypes.c_ulonglong), ("page_available", ctypes.c_ulonglong), ("virtual_total", ctypes.c_ulonglong), ("virtual_available", ctypes.c_ulonglong), ("extended", ctypes.c_ulonglong)]
                status = MemoryStatus(); status.length = ctypes.sizeof(status)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)): total = int(status.total)
            except (AttributeError, OSError, ValueError): total = None
        return _result(self, "available" if total is not None else "unsupported", {"total_bytes": total}, None if total is not None else "memory_probe_unsupported")


class StorageDetector(BaseDetector):
    detector_id, domain = "builtin_storage_v1", "storage"
    def detect(self, context: DetectionContext) -> Mapping[str, Any]:
        root = context.workspace_root
        if root is None: return _result(self, "unsupported", {}, "workspace_root_required")
        normalized = root.resolve(strict=False)
        reference = {"kind": "workspace_root", "name": normalized.name or "root"}
        if not normalized.exists(): return _result(self, "unavailable", {"workspace": reference}, "workspace_root_unavailable")
        try: usage = shutil.disk_usage(normalized)
        except OSError: return _result(self, "failed", {"workspace": reference}, "storage_probe_failed")
        return _result(self, "available", {"workspace": reference, "total_bytes": usage.total, "free_bytes": usage.free})


class ToolsDetector(BaseDetector):
    detector_id, domain = "builtin_tools_v1", "tools"
    def detect(self, context: DetectionContext) -> Mapping[str, Any]:
        tools = [{"tool_id": name, "available": shutil.which(name) is not None, "discovery_method": "executable_lookup"} for name in sorted(set(context.tool_allowlist))]
        return _result(self, "available", {"tools": tools})


class ModelsDetector(BaseDetector):
    detector_id, domain = "builtin_models_v1", "models"
    def detect(self, context: DetectionContext) -> Mapping[str, Any]: return _result(self, "unsupported", {"models": []}, "model_provider_not_configured")


class UnsupportedDetector(BaseDetector):
    def __init__(self, domain: str) -> None: self.domain, self.detector_id = domain, f"builtin_{domain}_v1"
    def detect(self, context: DetectionContext) -> Mapping[str, Any]: return _result(self, "unsupported", {}, f"{self.domain}_probe_unsupported")


def default_detector_providers() -> tuple[DetectorProvider, ...]:
    return (OperatingSystemDetector(), CpuDetector(), MemoryDetector(), StorageDetector(), ToolsDetector(), ModelsDetector(), UnsupportedDetector("accelerator"), UnsupportedDetector("network"), UnsupportedDetector("power"), UnsupportedDetector("execution_environment"))


class CapabilityDetectionOrchestrator:
    def __init__(self, providers: Iterable[DetectorProvider] | None = None) -> None:
        values = tuple(providers) if providers is not None else default_detector_providers()
        ids = [provider.detector_id for provider in values]
        if len(ids) != len(set(ids)): raise ValueError("duplicate_detector_id")
        if any(provider.domain not in DOMAINS or isinstance(provider.priority, bool) or not isinstance(provider.priority, int) for provider in values): raise ValueError("invalid_detector_provider")
        self._providers = tuple(sorted(values, key=_provider_sort))

    def list_detectors(self) -> list[dict[str, Any]]:
        return deepcopy([provider_metadata(provider) for provider in self._providers])

    def detect(self, domains: Iterable[str] | None = None, *, workspace_root: str | Path | None = None, observed_at: str | None = None) -> dict[str, Any]:
        requested = sorted(set(domains) if domains is not None else DOMAINS)
        if not requested or any(domain not in DOMAINS for domain in requested): raise ValueError("invalid_requested_domain")
        context = DetectionContext(Path(workspace_root) if workspace_root is not None else None)
        results = []
        for domain in requested:
            candidates = [provider for provider in self._providers if provider.domain == domain]
            if not candidates: raise ValueError("missing_detector_provider")
            provider = candidates[0]
            try:
                raw = provider.detect(context)
                result = deepcopy(dict(raw))
                if result.get("detector_id") != provider.detector_id or result.get("domain") != domain or result.get("status") not in STATUSES: raise ValueError("invalid_provider_result")
                json.loads(canonical_json(result))
            except Exception:
                result = _result(provider, "failed", {}, "detector_failed")
            results.append(result)
        statuses = {item["status"] for item in results}
        overall = "available" if statuses == {"available"} else "failed" if statuses == {"failed"} else "partial"
        metadata = self.list_detectors()
        base = {"schema": SCHEMA, "detection_version": DETECTION_VERSION, "observed_at": observed_at, "detector_set_fingerprint": compute_detector_set_fingerprint(metadata), "requested_domains": requested, "completed_domains": [item["domain"] for item in results], "overall_status": overall, "results": results, "warnings": sorted({item["error_code"] for item in results if item["error_code"]}), "source": {"kind": "explicit_local_detection"}}
        fingerprint = compute_detection_fingerprint(base)
        return json.loads(canonical_json({**base, "fingerprint": fingerprint, "detection_id": "capability-detection-" + fingerprint[:24]}))

    @staticmethod
    def detect_from_discovery_plan(plan: Any, domains: Iterable[str] | None = None, *, workspace_root: str | Path | None = None, observed_at: str | None = None) -> dict[str, Any]:
        """Explicit execution boundary. The inert discovery adapter never calls or creates providers."""
        requested = sorted(set(domains) if domains is not None else {p.domain for p in plan.providers} | {x["domain"] for x in plan.unbound_selections})
        bound_domains = {provider.domain for provider in plan.providers}
        bound_requested = [domain for domain in requested if domain in bound_domains]
        results = CapabilityDetectionOrchestrator(plan.providers).detect(bound_requested, workspace_root=workspace_root, observed_at=observed_at)["results"] if bound_requested else []
        for item in plan.unbound_selections:
            if item["domain"] in requested:
                results.append({"detector_id": item["detector_id"], "domain": item["domain"], "status": "unavailable", "evidence": {}, "error_code": "provider_unbound", "provider": {"schema": PROVIDER_SCHEMA, "provider_version": PROVIDER_VERSION, "detector_id": item["detector_id"], "domain": item["domain"], "priority": item["priority"], "supported_platforms": ["any"]}})
        results.sort(key=lambda item: item["domain"])
        statuses = {item["status"] for item in results}; overall = "available" if statuses == {"available"} else "failed" if statuses == {"failed"} else "partial"
        metadata = [item["provider"] for item in results]
        base = {"schema": SCHEMA, "detection_version": DETECTION_VERSION, "observed_at": observed_at, "detector_set_fingerprint": compute_detector_set_fingerprint(metadata), "requested_domains": requested, "completed_domains": [item["domain"] for item in results], "overall_status": overall, "results": results, "warnings": sorted({item["error_code"] for item in results if item["error_code"]}), "source": {"kind": "explicit_discovery_detection", "discovery_id": plan.discovery_id, "discovery_fingerprint": plan.discovery_fingerprint}}
        fingerprint = compute_detection_fingerprint(base)
        return json.loads(canonical_json({**base, "fingerprint": fingerprint, "detection_id": "capability-detection-" + fingerprint[:24]}))


def detection_to_profile_evidence(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {item["domain"]: deepcopy(item["evidence"]) for item in snapshot.get("results", []) if isinstance(item, Mapping)}


__all__ = ["SCHEMA", "DETECTION_VERSION", "PROVIDER_SCHEMA", "PROVIDER_VERSION", "DOMAINS", "STATUSES", "DetectorProvider", "DetectionContext", "CapabilityDetectionOrchestrator", "default_detector_providers", "provider_metadata", "compute_detector_set_fingerprint", "compute_detection_fingerprint", "compute_detection_id", "detection_to_profile_evidence"]

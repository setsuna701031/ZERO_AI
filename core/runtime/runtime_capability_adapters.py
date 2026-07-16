from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import sys
from typing import Any, Protocol


class CapabilityAdapter(Protocol):
    name: str
    section: str
    def detect(self) -> Any: ...


class OSAdapter:
    name, section = "operating_system", "operating_system"
    def detect(self) -> dict[str, Any]:
        return {"name": platform.system() or "unknown", "release": platform.release() or "unknown", "version": platform.version() or "unknown", "platform": platform.platform() or "unknown"}


class CPUAdapter:
    name, section = "cpu", "cpu"
    def detect(self) -> dict[str, Any]:
        return {"logical_cores": os.cpu_count() or 0, "physical_cores": None, "architecture": platform.machine() or "unknown", "processor": platform.processor() or "unknown"}


class MemoryAdapter:
    name, section = "memory", "memory"
    def detect(self) -> dict[str, Any]:
        return {"total_bytes": None, "available_bytes": None}


class StorageAdapter:
    name, section = "storage", "storage"
    def __init__(self, paths: tuple[str, ...] | None = None) -> None:
        self.paths = paths or (str(Path.cwd().anchor or Path.cwd()),)
    def detect(self) -> list[dict[str, Any]]:
        result = []
        for raw in self.paths:
            path = str(Path(raw).anchor or Path(raw))
            try:
                usage = shutil.disk_usage(path)
                result.append({"path": path, "total_bytes": usage.total, "free_bytes": usage.free})
            except OSError:
                result.append({"path": path, "total_bytes": None, "free_bytes": None})
        return result


class AcceleratorAdapter:
    name, section = "accelerators", "accelerators"
    def detect(self) -> list[dict[str, Any]]:
        # No driver probes, imports, servers, or workloads: unknown is explicit and safe.
        return []


class ToolAdapter:
    name, section = "available_tools", "available_tools"
    def __init__(self, allowlist: tuple[str, ...] = ("python", "git", "pytest")) -> None:
        self.allowlist = tuple(allowlist)
    def detect(self) -> list[dict[str, Any]]:
        return [{"name": name, "available": bool(shutil.which(name)), "path": Path(found).name if (found := shutil.which(name)) else None, "version": None} for name in self.allowlist]


class ModelAdapter:
    name, section = "installed_models", "installed_models"
    def detect(self) -> list[dict[str, Any]]:
        return []


class ExecutionEnvironmentAdapter:
    name, section = "execution_environment", "execution_environment"
    def detect(self) -> dict[str, Any]:
        env = os.environ
        wsl = bool(env.get("WSL_DISTRO_NAME")) or "microsoft" in platform.release().casefold()
        container = Path("/.dockerenv").exists()
        venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
        ci = any(env.get(key) for key in ("CI", "GITHUB_ACTIONS", "BUILD_BUILDID"))
        kind = "wsl" if wsl else "container" if container else "ci" if ci else "native"
        return {"kind": kind, "virtual_environment": venv, "container": container, "wsl": wsl, "ci": ci}


class PowerAdapter:
    name, section = "power", "power"
    def detect(self) -> dict[str, Any]:
        return {"source": "unknown", "battery_present": None, "constrained": None}


def default_adapters() -> tuple[CapabilityAdapter, ...]:
    return (OSAdapter(), CPUAdapter(), MemoryAdapter(), StorageAdapter(), AcceleratorAdapter(), ToolAdapter(), ModelAdapter(), ExecutionEnvironmentAdapter(), PowerAdapter())


__all__ = ["CapabilityAdapter", "OSAdapter", "CPUAdapter", "MemoryAdapter", "StorageAdapter", "AcceleratorAdapter", "ToolAdapter", "ModelAdapter", "ExecutionEnvironmentAdapter", "PowerAdapter", "default_adapters"]

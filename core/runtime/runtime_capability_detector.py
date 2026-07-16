from __future__ import annotations

import platform
import socket
import sys
import hashlib
from typing import Any, Iterable

from core.runtime.runtime_capability_adapters import CapabilityAdapter, default_adapters
from core.runtime.runtime_capability_profile import RuntimeCapabilityProfile


def _base_profile() -> dict[str, Any]:
    host_id = hashlib.sha256(socket.gethostname().encode("utf-8", errors="replace")).hexdigest()[:16]
    return {
        "host": {"hostname": f"host-{host_id}", "machine": platform.machine() or "unknown", "architecture": platform.architecture()[0] or "unknown", "processor": platform.processor() or "unknown"},
        "python_runtime": {"implementation": platform.python_implementation(), "version": platform.python_version(), "executable": "python" if sys.executable else "unknown"},
        "network": {"interfaces_detected": False, "outbound_connectivity_tested": False, "offline_safe": True},
        "constraints": [], "diagnostics": [],
        "operating_system": {"name": "unknown", "release": "unknown", "version": "unknown", "platform": "unknown"},
        "cpu": {"logical_cores": 0, "physical_cores": None, "architecture": "unknown", "processor": "unknown"},
        "memory": {"total_bytes": None, "available_bytes": None}, "storage": [], "accelerators": [],
        "execution_environment": {"kind": "unknown", "virtual_environment": False, "container": False, "wsl": False, "ci": False},
        "available_tools": [], "installed_models": [],
        "power": {"source": "unknown", "battery_present": None, "constrained": None},
    }


class RuntimeCapabilityDetector:
    def __init__(self, adapters: Iterable[CapabilityAdapter] | None = None) -> None:
        self.adapters = tuple(adapters) if adapters is not None else default_adapters()

    def detect(self, *, detected_at: str | None = None) -> RuntimeCapabilityProfile:
        content = _base_profile()
        for adapter in self.adapters:
            try:
                content[adapter.section] = adapter.detect()
            except Exception as exc:  # Adapter isolation is the fail-safe boundary.
                content["diagnostics"].append({"adapter": str(getattr(adapter, "name", "unknown"))[:64], "error_type": type(exc).__name__[:64], "reason_code": "adapter_detection_failed"})
        return RuntimeCapabilityProfile.create(content, detected_at=detected_at)


def detect_runtime_capabilities(*, detected_at: str | None = None, adapters: Iterable[CapabilityAdapter] | None = None) -> dict[str, Any]:
    return RuntimeCapabilityDetector(adapters).detect(detected_at=detected_at).to_dict()


__all__ = ["RuntimeCapabilityDetector", "detect_runtime_capabilities"]

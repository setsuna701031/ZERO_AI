from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RUNTIME_KERNEL_VERSION = "6.0.0"
RUNTIME_ABI_VERSION = "1.0"
RUNTIME_SCHEMA_FAMILY = "zero.runtime.kernel"


@dataclass(frozen=True)
class RuntimeVersionDescriptor:
    runtime_version: str = RUNTIME_KERNEL_VERSION
    abi_version: str = RUNTIME_ABI_VERSION
    schema_family: str = RUNTIME_SCHEMA_FAMILY
    phase: str = "kernel-seal"

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": self.runtime_version,
            "abi_version": self.abi_version,
            "schema_family": self.schema_family,
            "phase": self.phase,
        }


def runtime_version_descriptor() -> RuntimeVersionDescriptor:
    return RuntimeVersionDescriptor()


__all__ = [
    "RUNTIME_ABI_VERSION",
    "RUNTIME_KERNEL_VERSION",
    "RUNTIME_SCHEMA_FAMILY",
    "RuntimeVersionDescriptor",
    "runtime_version_descriptor",
]

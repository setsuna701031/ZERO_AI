from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from core.runtime.runtime_integrity import stable_fingerprint
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


_JSON_PRIMITIVES = (str, int, float, bool, type(None))


def _normalize(value: Any) -> Any:
    if isinstance(value, _JSON_PRIMITIVES):
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in sorted(value.keys(), key=lambda item: str(item)):
            if str(key) == "runtime_seal":
                normalized[str(key)] = _normalize(value[key])
            else:
                normalized[str(key)] = _normalize(value[key])
        return normalized
    if isinstance(value, (list, tuple, set, frozenset)):
        if isinstance(value, (set, frozenset)):
            return [_normalize(item) for item in sorted(value, key=lambda item: json.dumps(_normalize(item), sort_keys=True, default=str))]
        return [_normalize(item) for item in value]
    if hasattr(value, "to_dict"):
        return _normalize(value.to_dict())
    return str(value)


@dataclass(frozen=True)
class RuntimeSerializedArtifact:
    artifact_type: str
    payload: dict[str, Any]
    canonical_json: str
    fingerprint: str
    runtime_version: str = RUNTIME_KERNEL_VERSION
    abi_version: str = RUNTIME_ABI_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_version": self.runtime_version,
            "abi_version": self.abi_version,
            "artifact_type": "runtime_serialized_artifact",
            "serialized_artifact_type": self.artifact_type,
            "fingerprint": self.fingerprint,
            "canonical_json": self.canonical_json,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
        }


class RuntimeSerializationAuthority:
    """Canonical serializer for runtime object graph artifacts.

    Keep this layer small and deterministic.  It exists to prevent ABI/evidence/
    replay drift caused by each runtime subsystem inventing its own JSON shape.
    """

    def normalize(self, payload: Any, *, artifact_type: str = "runtime_artifact") -> dict[str, Any]:
        normalized = _normalize(payload)
        if not isinstance(normalized, dict):
            normalized = {"value": normalized}
        normalized.setdefault("runtime_version", RUNTIME_KERNEL_VERSION)
        normalized.setdefault("abi_version", RUNTIME_ABI_VERSION)
        normalized.setdefault("artifact_type", artifact_type)
        return normalized

    def canonical_json(self, payload: Any, *, artifact_type: str = "runtime_artifact") -> str:
        normalized = self.normalize(payload, artifact_type=artifact_type)
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)

    def fingerprint(self, payload: Any, *, artifact_type: str = "runtime_artifact") -> str:
        normalized = self.normalize(payload, artifact_type=artifact_type)
        return stable_fingerprint(normalized)

    def serialize(
        self,
        payload: Any,
        *,
        artifact_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeSerializedArtifact:
        normalized = self.normalize(payload, artifact_type=artifact_type)
        canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return RuntimeSerializedArtifact(
            artifact_type=artifact_type,
            payload=normalized,
            canonical_json=canonical,
            fingerprint=stable_fingerprint(normalized),
            metadata=copy.deepcopy(dict(metadata or {})),
        )


DEFAULT_RUNTIME_SERIALIZER = RuntimeSerializationAuthority()


__all__ = [
    "DEFAULT_RUNTIME_SERIALIZER",
    "RuntimeSerializedArtifact",
    "RuntimeSerializationAuthority",
]

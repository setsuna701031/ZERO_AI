from __future__ import annotations

"""Dependency-neutral, versioned result projection contract."""

import json
import math
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RuntimeResultProjectionContract:
    identity: str = "zero.runtime_result_projection"
    version: str = "v1"
    allowed_fields: tuple[str, ...] = ()
    maximum_depth: int = 6
    maximum_items: int = 50
    maximum_string_chars: int = 8192
    maximum_size_bytes: int = 1024 * 1024
    cycle_marker: str = "<recursive_reference>"

    def contract_hash(self) -> str:
        payload = {
            "identity": self.identity,
            "version": self.version,
            "allowed_fields": self.allowed_fields,
            "maximum_depth": self.maximum_depth,
            "maximum_items": self.maximum_items,
            "maximum_string_chars": self.maximum_string_chars,
            "maximum_size_bytes": self.maximum_size_bytes,
            "cycle_marker": self.cycle_marker,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def project(self, value: Any) -> Any:
        source = value
        if self.allowed_fields and isinstance(value, Mapping):
            source = {key: value.get(key) for key in self.allowed_fields if key in value}
        projected = bounded_json_projection(
            source,
            max_depth=self.maximum_depth,
            max_items=self.maximum_items,
            max_string_chars=self.maximum_string_chars,
            cycle_marker=self.cycle_marker,
            initial_active_ids={id(value)} if source is not value else None,
        )
        encoded = json.dumps(projected, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) <= self.maximum_size_bytes:
            return projected
        return {
            "projection_contract": self.identity,
            "projection_version": self.version,
            "projection_compacted": True,
            "original_size_bytes": len(encoded),
        }


DEFAULT_RUNTIME_RESULT_PROJECTION_CONTRACT = RuntimeResultProjectionContract()


def detach_internal_result(value: Any, *, _memo: dict[int, Any] | None = None) -> Any:
    """Detach internal execution structures without truncation or sentinels.

    This is intentionally separate from public projection. It preserves every
    mapping/list item and reconstructs cycles through a memoized target graph.
    """

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return bytes(value)
    if isinstance(value, bytearray):
        return bytearray(value)

    memo = _memo if _memo is not None else {}
    identity = id(value)
    if identity in memo:
        return memo[identity]

    if isinstance(value, Mapping):
        detached: dict[Any, Any] = {}
        memo[identity] = detached
        for key, item in value.items():
            detached[detach_internal_result(key, _memo=memo)] = detach_internal_result(item, _memo=memo)
        return detached
    if isinstance(value, list):
        detached_list: list[Any] = []
        memo[identity] = detached_list
        detached_list.extend(detach_internal_result(item, _memo=memo) for item in value)
        return detached_list
    if isinstance(value, tuple):
        # Runtime payload tuples are transported as JSON-compatible lists.
        detached_tuple: list[Any] = []
        memo[identity] = detached_tuple
        detached_tuple.extend(detach_internal_result(item, _memo=memo) for item in value)
        return detached_tuple
    if isinstance(value, (set, frozenset)):
        detached_set: list[Any] = []
        memo[identity] = detached_set
        detached_set.extend(
            detach_internal_result(item, _memo=memo)
            for item in sorted(value, key=lambda item: repr(item))
        )
        return detached_set
    # Opaque authority/evidence objects retain their type and issuance identity;
    # converting them through to_dict() would invalidate authority seals.
    return value


ProjectionAdapter = Callable[[Any], Any]


@dataclass(frozen=True)
class ProjectionAdapterManifest:
    adapter_id: str
    name: str
    owner_domain: str
    contract_version: str
    contract_hash: str
    output_schema: str
    max_payload_bytes: int
    required_fields: tuple[str, ...] = ()
    status: str = "active"


class ProjectionAdapterRegistry:
    """Consumer adapters governed by one versioned projection contract."""

    def __init__(self, contract: RuntimeResultProjectionContract) -> None:
        self.contract = contract
        self._adapters: dict[str, tuple[ProjectionAdapterManifest, ProjectionAdapter]] = {}
        self._health_counters = {"payload_violations": 0, "version_mismatch": 0, "schema_drift": 0}

    def register(
        self,
        consumer: str,
        adapter: ProjectionAdapter | None = None,
        *,
        adapter_id: str,
        owner_domain: str,
        contract_version: str,
        contract_hash: str,
        output_schema: str,
        max_payload_bytes: int,
        required_fields: tuple[str, ...] = (),
        status: str = "active",
    ) -> None:
        name = str(consumer or "").strip().lower()
        if not name:
            raise ValueError("projection_adapter_consumer_required")
        if name in self._adapters:
            raise ValueError(f"projection_adapter_already_registered:{name}")
        if contract_version != self.contract.version:
            self._health_counters["version_mismatch"] += 1
            raise ValueError(
                f"projection_adapter_contract_version_incompatible:{name}:{contract_version}:{self.contract.version}"
            )
        if contract_hash != self.contract.contract_hash():
            self._health_counters["version_mismatch"] += 1
            raise ValueError(f"projection_adapter_contract_hash_mismatch:{name}")
        identifier = str(adapter_id or "").strip()
        domain = str(owner_domain or "").strip().lower()
        if not identifier:
            raise ValueError(f"projection_adapter_id_required:{name}")
        if not domain:
            raise ValueError(f"projection_adapter_owner_domain_required:{name}")
        normalized_status = str(status or "active").strip().lower()
        if normalized_status not in {"active", "deprecated", "disabled"}:
            raise ValueError(f"projection_adapter_status_invalid:{name}")
        payload_limit = int(max_payload_bytes)
        if payload_limit <= 0 or payload_limit > self.contract.maximum_size_bytes:
            raise ValueError(f"projection_adapter_payload_limit_invalid:{name}")
        schema = str(output_schema or "").strip()
        if not schema:
            raise ValueError(f"projection_adapter_output_schema_required:{name}")
        manifest = ProjectionAdapterManifest(
            adapter_id=identifier,
            name=name,
            owner_domain=domain,
            contract_version=contract_version,
            contract_hash=contract_hash,
            output_schema=schema,
            max_payload_bytes=payload_limit,
            required_fields=tuple(required_fields),
            status=normalized_status,
        )
        self._adapters[name] = (manifest, adapter or (lambda value: value))

    def project(self, consumer: str, value: Any) -> Any:
        name = str(consumer or "").strip().lower()
        try:
            manifest, adapter = self._adapters[name]
        except KeyError as exc:
            raise KeyError(f"projection_adapter_not_registered:{name}") from exc
        # The contract is always applied last, so adapters cannot bypass limits.
        projected = self.contract.project(adapter(value))
        if manifest.required_fields:
            if not isinstance(projected, Mapping):
                raise ValueError(f"projection_adapter_mapping_output_required:{name}")
            missing = [field for field in manifest.required_fields if field not in projected]
            if missing:
                self._health_counters["schema_drift"] += 1
                raise ValueError(f"projection_adapter_required_fields_missing:{name}:{','.join(missing)}")
        size = len(json.dumps(projected, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if size > manifest.max_payload_bytes:
            self._health_counters["payload_violations"] += 1
            raise ValueError(f"projection_adapter_payload_limit_exceeded:{name}:{size}")
        return projected

    def consumers(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def manifest(self, consumer: str) -> ProjectionAdapterManifest:
        name = str(consumer or "").strip().lower()
        try:
            return self._adapters[name][0]
        except KeyError as exc:
            raise KeyError(f"projection_adapter_not_registered:{name}") from exc

    def compatibility_report(self, target_version: str) -> dict[str, tuple[str, ...]]:
        compatible: list[str] = []
        incompatible: list[str] = []
        upgrade_required: list[str] = []
        for name, (manifest, _) in sorted(self._adapters.items()):
            if manifest.contract_version == target_version:
                compatible.append(name)
            elif manifest.contract_version == self.contract.version:
                upgrade_required.append(name)
            else:
                incompatible.append(name)
        return {
            "compatible": tuple(compatible),
            "incompatible": tuple(incompatible),
            "upgrade_required": tuple(upgrade_required),
        }

    def dependency_graph(self) -> dict[str, Any]:
        return {
            "contract": {
                "identity": self.contract.identity,
                "version": self.contract.version,
                "contract_hash": self.contract.contract_hash(),
            },
            "adapters": [
                {
                    "name": manifest.name,
                    "adapter_id": manifest.adapter_id,
                    "owner_domain": manifest.owner_domain,
                    "contract_version": manifest.contract_version,
                    "output_schema": manifest.output_schema,
                    "status": manifest.status,
                }
                for manifest, _ in (self._adapters[name] for name in sorted(self._adapters))
            ],
        }

    def upgrade_impact(self, target_version: str) -> dict[str, Any]:
        report = self.compatibility_report(target_version)
        affected = tuple(sorted(set(report["incompatible"] + report["upgrade_required"])))
        return {
            "current_version": self.contract.version,
            "target_version": str(target_version),
            "affected_adapters": affected,
            "affected_owner_domains": tuple(
                sorted({self.manifest(name).owner_domain for name in affected})
            ),
            "compatibility": report,
        }

    def health(self) -> dict[str, Any]:
        current_hash = self.contract.contract_hash()
        adapters = {
            name: {
                "adapter_id": manifest.adapter_id,
                "owner_domain": manifest.owner_domain,
                "status": manifest.status,
                "contract_version": manifest.contract_version,
                "contract_hash_valid": manifest.contract_hash == current_hash,
                "output_schema": manifest.output_schema,
                "max_payload_bytes": manifest.max_payload_bytes,
            }
            for name, (manifest, _) in sorted(self._adapters.items())
        }
        healthy = sum(
            1
            for item in adapters.values()
            if item["status"] == "active" and item["contract_hash_valid"]
        )
        active = sum(1 for item in adapters.values() if item["status"] == "active")
        return {
            "contract_identity": self.contract.identity,
            "contract_version": self.contract.version,
            "contract_hash": current_hash,
            "contract_coverage_percent": 100.0 if active == 0 else round(healthy * 100.0 / active, 2),
            **self._health_counters,
            "adapters": adapters,
            "dependency_graph": self.dependency_graph(),
        }


RUNTIME_RESULT_PROJECTION_ADAPTERS = ProjectionAdapterRegistry(
    DEFAULT_RUNTIME_RESULT_PROJECTION_CONTRACT
)
for _consumer, (_schema, _domain, _status) in {
    "cli": ("CliResultProjection", "cli", "active"),
    "dashboard": ("DashboardProjection", "operator", "active"),
    "evidence": ("EvidenceProjection", "evidence", "active"),
    "memory": ("MemoryProjection", "memory", "active"),
    "persistence": ("PersistenceProjection", "runtime", "active"),
    "resume": ("ResumeProjection", "runtime", "active"),
}.items():
    RUNTIME_RESULT_PROJECTION_ADAPTERS.register(
        _consumer,
        adapter_id=f"projection-adapter:{_consumer}:v1",
        owner_domain=_domain,
        contract_version="v1",
        contract_hash=DEFAULT_RUNTIME_RESULT_PROJECTION_CONTRACT.contract_hash(),
        output_schema=_schema,
        max_payload_bytes=1024 * 1024,
        status=_status,
    )


def project_result_for(consumer: str, value: Any) -> Any:
    return RUNTIME_RESULT_PROJECTION_ADAPTERS.project(consumer, value)


def bounded_json_projection(
    value: Any,
    *,
    max_depth: int = 6,
    max_items: int = 50,
    max_string_chars: int = 8192,
    cycle_marker: str = "<recursive_reference>",
    initial_active_ids: set[int] | None = None,
) -> Any:
    active: set[int] = set(initial_active_ids or ())

    def project(item: Any, depth: int) -> Any:
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            return item if math.isfinite(item) else str(item)
        if isinstance(item, str):
            return item if len(item) <= max_string_chars else item[:max_string_chars] + "...<truncated>"
        if isinstance(item, (bytes, bytearray)):
            text = bytes(item[:max_string_chars]).decode("utf-8", errors="replace")
            return text + ("...<truncated>" if len(item) > max_string_chars else "")
        if depth >= max_depth:
            return "<max_depth_reached>"
        identity = id(item)
        if identity in active:
            return cycle_marker
        if isinstance(item, Mapping):
            active.add(identity)
            try:
                result: dict[str, Any] = {}
                for count, (key, child) in enumerate(item.items()):
                    if count >= max_items:
                        result["_truncated_items"] = True
                        break
                    result[str(key)] = project(child, depth + 1)
                return result
            finally:
                active.remove(identity)
        if isinstance(item, (list, tuple)):
            active.add(identity)
            try:
                result = [project(child, depth + 1) for child in item[:max_items]]
                if len(item) > max_items:
                    result.append({"_truncated_items": len(item) - max_items})
                return result
            finally:
                active.remove(identity)
        if isinstance(item, (set, frozenset)):
            return sorted((project(child, depth + 1) for child in list(item)[:max_items]), key=str)
        to_dict = getattr(item, "to_dict", None)
        if callable(to_dict):
            active.add(identity)
            try:
                return project(to_dict(), depth + 1)
            except Exception:
                return f"<{type(item).__name__}>"
            finally:
                active.remove(identity)
        return f"<{type(item).__name__}>"

    return project(value, 0)


def mapping_projection(value: Any, **limits: Any) -> dict[str, Any]:
    projected = bounded_json_projection(value, **limits)
    return projected if isinstance(projected, dict) else {}


__all__ = [
    "DEFAULT_RUNTIME_RESULT_PROJECTION_CONTRACT",
    "ProjectionAdapterRegistry",
    "ProjectionAdapterManifest",
    "RUNTIME_RESULT_PROJECTION_ADAPTERS",
    "RuntimeResultProjectionContract",
    "bounded_json_projection",
    "detach_internal_result",
    "mapping_projection",
    "project_result_for",
]

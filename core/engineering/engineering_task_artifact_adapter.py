from __future__ import annotations
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence
from core.engineering.engineering_mutation_transaction_common import fingerprint
from core.engineering.engineering_task_artifact_reference import build_artifact_reference

ADAPTER_SCHEMA = "zero.engineering.task_artifact_adapter.v1"
VALIDATION_LEVELS = frozenset({"canonical_validator", "canonical_builder_result", "structural_reference_only"})

class ArtifactAdapterError(ValueError):
    pass

@dataclass(frozen=True)
class ArtifactAdapterDescriptor:
    phase: str
    supported_schema: str
    production_module: str
    validator_entry_point: str
    identity_field: str
    fingerprint_field: str = "fingerprint"
    status_field: str = "status"
    accepted_statuses: tuple[str, ...] = ()
    rejected_statuses: tuple[str, ...] = ()
    linkage_fields: tuple[str, ...] = ()
    validation_level: str = "canonical_validator"
    immutable: bool = True
    deterministic: bool = True
    payload_size_limit: int = 65536
    adapter_version: str = "1"

    @property
    def adapter_id(self) -> str:
        return "engineering-task-artifact-adapter-" + fingerprint(self._stable(False))[:24]

    @property
    def adapter_fingerprint(self) -> str:
        return fingerprint(self._stable(True))

    def _stable(self, include_id: bool) -> dict[str, Any]:
        d = {
            "schema": ADAPTER_SCHEMA,
            "adapter_version": self.adapter_version,
            "phase": self.phase,
            "supported_schema": self.supported_schema,
            "production_module": self.production_module,
            "validator_entry_point": self.validator_entry_point,
            "identity_field": self.identity_field,
            "fingerprint_field": self.fingerprint_field,
            "status_field": self.status_field,
            "accepted_statuses": sorted(self.accepted_statuses),
            "rejected_statuses": sorted(self.rejected_statuses),
            "linkage_fields": sorted(self.linkage_fields),
            "validation_level": self.validation_level,
            "immutable": self.immutable,
            "deterministic": self.deterministic,
            "payload_size_limit": self.payload_size_limit,
        }
        if include_id:
            d["adapter_id"] = self.adapter_id
        return d

    def as_dict(self) -> dict[str, Any]:
        d = self._stable(True)
        d["adapter_fingerprint"] = self.adapter_fingerprint
        return d

@dataclass(frozen=True)
class EngineeringTaskArtifactAdapter:
    descriptor: ArtifactAdapterDescriptor
    validator: Callable[[Any], Any]

    def __post_init__(self) -> None:
        if self.descriptor.validation_level not in VALIDATION_LEVELS:
            raise ArtifactAdapterError("invalid_validation_level")
        if self.descriptor.validation_level == "structural_reference_only" and "validate" in self.descriptor.validator_entry_point:
            raise ArtifactAdapterError("structural_adapter_misclassified")

    def validate(self, artifact: Any) -> Mapping[str, Any]:
        if not isinstance(artifact, Mapping):
            raise ArtifactAdapterError("artifact_not_mapping")
        from core.engineering.engineering_mutation_transaction_common import canonical_json
        if len(canonical_json(artifact).encode()) > self.descriptor.payload_size_limit:
            raise ArtifactAdapterError("artifact_payload_too_large")
        if artifact.get("schema") != self.descriptor.supported_schema:
            raise ArtifactAdapterError("schema_mismatch")
        result = self.validator(artifact)
        valid = bool(result.get("valid")) if isinstance(result, Mapping) else bool(getattr(result, "valid", False))
        errors = tuple(result.get("errors", ())) if isinstance(result, Mapping) else tuple(getattr(result, "errors", ()))
        status = str(artifact.get(self.descriptor.status_field) or "")
        if not valid:
            raise ArtifactAdapterError("canonical_rejection:" + ",".join(errors or ("invalid",)))
        if status not in set(self.descriptor.accepted_statuses):
            raise ArtifactAdapterError("status_not_accepted")
        if status in set(self.descriptor.rejected_statuses):
            raise ArtifactAdapterError("status_rejected")
        identity = artifact.get(self.descriptor.identity_field)
        afp = artifact.get(self.descriptor.fingerprint_field)
        if not isinstance(identity, str) or not identity:
            raise ArtifactAdapterError("identity_missing")
        if not isinstance(afp, str) or len(afp) != 64 or any(c not in "0123456789abcdef" for c in afp):
            raise ArtifactAdapterError("fingerprint_malformed")
        linkage = {k: artifact.get(k) for k in self.descriptor.linkage_fields if artifact.get(k) is not None}
        summary = {"status": status, "identity_field": self.descriptor.identity_field}
        return build_artifact_reference(phase=self.descriptor.phase, schema=self.descriptor.supported_schema,
            artifact_identity=identity, artifact_fingerprint=afp, adapter_id=self.descriptor.adapter_id,
            adapter_version=self.descriptor.adapter_version, validation_level=self.descriptor.validation_level,
            validation_status=status, linkage=linkage, bounded_summary=summary)

__all__ = ["ADAPTER_SCHEMA", "ArtifactAdapterDescriptor", "EngineeringTaskArtifactAdapter", "ArtifactAdapterError"]

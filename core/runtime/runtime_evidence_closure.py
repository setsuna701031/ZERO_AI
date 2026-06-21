from __future__ import annotations

"""Runtime evidence closure contract.

This module seals the identity handoff between runtime identity, evidence,
persistence, and resume.  It is intentionally passive: it validates and
fingerprints an already-issued identity graph and evidence payloads, but it does
not mint authority, capability, execution, session, lineage, or evidence IDs.
"""

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

RUNTIME_EVIDENCE_CLOSURE_SCHEMA = "zero.runtime_evidence_closure.v1"

IDENTITY_FIELDS = (
    "goal_id",
    "root_goal_id",
    "source_goal_id",
    "goal_lineage_id",
    "branch_id",
    "branch_type",
    "session_id",
    "runtime_session_id",
    "execution_id",
    "capability_id",
)

EVIDENCE_FIELDS = ("evidence_id",)

FORBIDDEN_SENTINEL_IDENTITIES = {
    "",
    "unknown",
    "default",
    "legacy",
    "runtime",
    "system",
    "none",
    "null",
    "undefined",
}

_NESTED_IDENTITY_KEYS = (
    "identity_graph",
    "runtime_identity_graph",
    "canonical_identity_graph",
    "identity",
    "runtime_identity",
    "goal_lineage",
    "lineage",
    "metadata",
    "payload",
    "runtime_evidence",
    "evidence",
    "runtime_capability_graph",
    "capability_graph",
    "persistence",
    "resume",
    "recovery",
    "execution",
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        return copy.deepcopy(dict(result)) if isinstance(result, Mapping) else {}
    return {}


def _collect_field(source: Mapping[str, Any], field: str) -> str:
    direct = _text(source.get(field))
    if direct:
        return direct
    for key in _NESTED_IDENTITY_KEYS:
        nested = source.get(key)
        if isinstance(nested, Mapping):
            found = _collect_field(nested, field)
            if found:
                return found
    return ""


def _canonical_subset(source: Mapping[str, Any], fields: Sequence[str]) -> dict[str, str]:
    return {field: _collect_field(source, field) for field in fields}


def _reject_forbidden(identity: Mapping[str, str], *, fields: Sequence[str]) -> None:
    for field in fields:
        value = _text(identity.get(field))
        if value.lower() in FORBIDDEN_SENTINEL_IDENTITIES:
            raise ValueError(f"runtime_evidence_forbidden_identity:{field}")


def _require(identity: Mapping[str, str], *, fields: Sequence[str]) -> None:
    missing = [field for field in fields if not _text(identity.get(field))]
    if missing:
        raise ValueError("runtime_evidence_identity_missing:" + ",".join(missing))


def _stable_fingerprint(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeEvidenceIdentityGraph:
    goal_id: str
    root_goal_id: str
    source_goal_id: str
    goal_lineage_id: str
    branch_id: str
    branch_type: str
    session_id: str
    runtime_session_id: str
    execution_id: str
    capability_id: str

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "RuntimeEvidenceIdentityGraph":
        identity = _canonical_subset(source, IDENTITY_FIELDS)
        _require(identity, fields=IDENTITY_FIELDS)
        _reject_forbidden(identity, fields=IDENTITY_FIELDS)
        return cls(**identity)

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in IDENTITY_FIELDS}

    @property
    def fingerprint(self) -> str:
        return _stable_fingerprint(self.to_dict())


@dataclass(frozen=True)
class RuntimeEvidenceClosureRecord:
    evidence_id: str
    identity_graph: RuntimeEvidenceIdentityGraph
    evidence_fingerprint: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUNTIME_EVIDENCE_CLOSURE_SCHEMA,
            "evidence_id": self.evidence_id,
            "identity_graph": self.identity_graph.to_dict(),
            "identity_fingerprint": self.identity_graph.fingerprint,
            "evidence_fingerprint": self.evidence_fingerprint,
            "payload": copy.deepcopy(self.payload),
        }


def seal_runtime_evidence(
    evidence: Mapping[str, Any],
    *,
    identity_graph: RuntimeEvidenceIdentityGraph | Mapping[str, Any],
) -> RuntimeEvidenceClosureRecord:
    """Bind evidence to an already-canonical identity graph.

    The caller must pass the identity graph produced by the runtime identity
    closure path.  This function rejects evidence that omits or contradicts that
    graph; it never fills missing identity values with fallback IDs.
    """

    canonical = (
        identity_graph
        if isinstance(identity_graph, RuntimeEvidenceIdentityGraph)
        else RuntimeEvidenceIdentityGraph.from_mapping(identity_graph)
    )
    payload = _mapping(evidence)
    if not payload:
        raise ValueError("runtime_evidence_payload_required")

    evidence_identity = _canonical_subset(payload, IDENTITY_FIELDS)
    present = {key: value for key, value in evidence_identity.items() if _text(value)}
    if present:
        _reject_forbidden(evidence_identity, fields=present.keys())
    for field, expected in canonical.to_dict().items():
        actual = _text(evidence_identity.get(field))
        if actual and actual != expected:
            raise ValueError(f"runtime_evidence_identity_drift:{field}")

    evidence_id = _collect_field(payload, "evidence_id")
    if not evidence_id or evidence_id.lower() in FORBIDDEN_SENTINEL_IDENTITIES:
        raise ValueError("runtime_evidence_id_required")

    sealed_payload = copy.deepcopy(payload)
    sealed_payload["identity_graph"] = canonical.to_dict()
    sealed_payload["identity_fingerprint"] = canonical.fingerprint
    sealed_payload["evidence_id"] = evidence_id
    return RuntimeEvidenceClosureRecord(
        evidence_id=evidence_id,
        identity_graph=canonical,
        evidence_fingerprint=_stable_fingerprint(sealed_payload),
        payload=sealed_payload,
    )


def validate_runtime_evidence_chain(
    identity_graph: RuntimeEvidenceIdentityGraph | Mapping[str, Any],
    evidence_items: Sequence[Mapping[str, Any]],
    *,
    persistence_record: Mapping[str, Any] | None = None,
    resume_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    canonical = (
        identity_graph
        if isinstance(identity_graph, RuntimeEvidenceIdentityGraph)
        else RuntimeEvidenceIdentityGraph.from_mapping(identity_graph)
    )
    if not evidence_items:
        raise ValueError("runtime_evidence_chain_required")

    sealed = [seal_runtime_evidence(item, identity_graph=canonical) for item in evidence_items]
    evidence_ids = [item.evidence_id for item in sealed]
    if len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError("runtime_evidence_id_reissue")

    for label, record in (("persistence", persistence_record), ("resume", resume_record)):
        if record is None:
            continue
        graph = RuntimeEvidenceIdentityGraph.from_mapping(record)
        if graph.to_dict() != canonical.to_dict():
            raise ValueError(f"runtime_evidence_{label}_identity_drift")
        fingerprint = _collect_field(record, "identity_fingerprint")
        if fingerprint and fingerprint != canonical.fingerprint:
            raise ValueError(f"runtime_evidence_{label}_fingerprint_drift")
        refs = record.get("evidence_ids") or record.get("evidence_refs")
        if isinstance(refs, Sequence) and not isinstance(refs, (str, bytes)):
            missing = sorted(set(evidence_ids) - {_text(item) for item in refs})
            if missing:
                raise ValueError(f"runtime_evidence_{label}_missing_refs:" + ",".join(missing))

    return {
        "schema": RUNTIME_EVIDENCE_CLOSURE_SCHEMA,
        "valid": True,
        "identity_graph": canonical.to_dict(),
        "identity_fingerprint": canonical.fingerprint,
        "evidence_ids": evidence_ids,
        "evidence_fingerprints": [item.evidence_fingerprint for item in sealed],
    }


__all__ = [
    "FORBIDDEN_SENTINEL_IDENTITIES",
    "IDENTITY_FIELDS",
    "RUNTIME_EVIDENCE_CLOSURE_SCHEMA",
    "RuntimeEvidenceClosureRecord",
    "RuntimeEvidenceIdentityGraph",
    "seal_runtime_evidence",
    "validate_runtime_evidence_chain",
]

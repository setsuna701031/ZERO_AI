from __future__ import annotations

"""Runtime persistence closure contract.

This module seals the handoff from the live runtime execution graph into
persistence, snapshots, resume, and recovered runtime state.  It is passive by
construction: it validates and fingerprints an already-issued authority /
capability / identity / evidence graph, but it never mints replacement IDs.
"""

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

RUNTIME_PERSISTENCE_CLOSURE_SCHEMA = "zero.runtime_persistence_closure.v1"

EXECUTION_GRAPH_FIELDS = (
    "goal_id",
    "root_goal_id",
    "source_goal_id",
    "goal_lineage_id",
    "branch_id",
    "branch_type",
    "session_id",
    "runtime_session_id",
    "execution_id",
    "authority_decision_id",
    "capability_id",
)

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

_NESTED_KEYS = (
    "execution_graph",
    "runtime_execution_graph",
    "identity_graph",
    "runtime_identity_graph",
    "canonical_identity_graph",
    "authority_graph",
    "capability_graph",
    "runtime_capability_graph",
    "evidence_graph",
    "runtime_evidence_graph",
    "persistence_graph",
    "snapshot_graph",
    "resume_graph",
    "recovered_graph",
    "recovery_graph",
    "metadata",
    "payload",
    "persistence",
    "snapshot",
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
    for key in _NESTED_KEYS:
        nested = source.get(key)
        if isinstance(nested, Mapping):
            found = _collect_field(nested, field)
            if found:
                return found
    return ""


def _stable_fingerprint(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reject_forbidden(values: Mapping[str, str], *, fields: Sequence[str]) -> None:
    for field in fields:
        value = _text(values.get(field))
        if value.lower() in FORBIDDEN_SENTINEL_IDENTITIES:
            raise ValueError(f"runtime_persistence_forbidden_identity:{field}")


def _require(values: Mapping[str, str], *, fields: Sequence[str]) -> None:
    missing = [field for field in fields if not _text(values.get(field))]
    if missing:
        raise ValueError("runtime_persistence_graph_missing:" + ",".join(missing))


def _canonical_subset(source: Mapping[str, Any]) -> dict[str, str]:
    return {field: _collect_field(source, field) for field in EXECUTION_GRAPH_FIELDS}


def _evidence_ids(source: Mapping[str, Any]) -> tuple[str, ...]:
    raw = source.get("evidence_ids") or source.get("evidence_refs") or source.get("evidence_id")
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        values = [_text(item) for item in raw]
    else:
        values = []
    cleaned = tuple(value for value in values if value)
    if any(value.lower() in FORBIDDEN_SENTINEL_IDENTITIES for value in cleaned):
        raise ValueError("runtime_persistence_forbidden_evidence_ref")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("runtime_persistence_evidence_ref_reissue")
    return cleaned


@dataclass(frozen=True)
class RuntimePersistenceExecutionGraph:
    goal_id: str
    root_goal_id: str
    source_goal_id: str
    goal_lineage_id: str
    branch_id: str
    branch_type: str
    session_id: str
    runtime_session_id: str
    execution_id: str
    authority_decision_id: str
    capability_id: str

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "RuntimePersistenceExecutionGraph":
        graph = _canonical_subset(source)
        _require(graph, fields=EXECUTION_GRAPH_FIELDS)
        _reject_forbidden(graph, fields=EXECUTION_GRAPH_FIELDS)
        return cls(**graph)

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in EXECUTION_GRAPH_FIELDS}

    @property
    def fingerprint(self) -> str:
        return _stable_fingerprint(self.to_dict())


@dataclass(frozen=True)
class RuntimePersistenceClosureRecord:
    persistence_id: str
    execution_graph: RuntimePersistenceExecutionGraph
    evidence_ids: tuple[str, ...]
    persistence_fingerprint: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUNTIME_PERSISTENCE_CLOSURE_SCHEMA,
            "persistence_id": self.persistence_id,
            "execution_graph": self.execution_graph.to_dict(),
            "execution_fingerprint": self.execution_graph.fingerprint,
            "evidence_ids": list(self.evidence_ids),
            "persistence_fingerprint": self.persistence_fingerprint,
            "payload": copy.deepcopy(self.payload),
        }


def seal_runtime_persistence(
    persistence_record: Mapping[str, Any],
    *,
    execution_graph: RuntimePersistenceExecutionGraph | Mapping[str, Any],
    evidence_ids: Sequence[str] | None = None,
) -> RuntimePersistenceClosureRecord:
    """Bind persisted state to the canonical live execution graph.

    Existing persisted identity values are allowed only when they match the live
    graph.  Missing graph fields are not backfilled from fallback identifiers;
    the canonical graph must be supplied by the caller.
    """

    canonical = (
        execution_graph
        if isinstance(execution_graph, RuntimePersistenceExecutionGraph)
        else RuntimePersistenceExecutionGraph.from_mapping(execution_graph)
    )
    payload = _mapping(persistence_record)
    if not payload:
        raise ValueError("runtime_persistence_payload_required")

    persistence_id = _collect_field(payload, "persistence_id") or _collect_field(payload, "snapshot_id")
    if not persistence_id or persistence_id.lower() in FORBIDDEN_SENTINEL_IDENTITIES:
        raise ValueError("runtime_persistence_id_required")

    present_graph = _canonical_subset(payload)
    present_fields = [field for field, value in present_graph.items() if _text(value)]
    if present_fields:
        _reject_forbidden(present_graph, fields=present_fields)
    for field, expected in canonical.to_dict().items():
        actual = _text(present_graph.get(field))
        if actual and actual != expected:
            raise ValueError(f"runtime_persistence_graph_drift:{field}")

    refs = tuple(_text(item) for item in (evidence_ids or ()))
    refs = tuple(value for value in refs if value)
    if refs and len(set(refs)) != len(refs):
        raise ValueError("runtime_persistence_evidence_ref_reissue")
    persisted_refs = _evidence_ids(payload)
    if refs and persisted_refs and set(refs) != set(persisted_refs):
        raise ValueError("runtime_persistence_evidence_ref_drift")
    sealed_refs = persisted_refs or refs

    sealed_payload = copy.deepcopy(payload)
    sealed_payload["execution_graph"] = canonical.to_dict()
    sealed_payload["execution_fingerprint"] = canonical.fingerprint
    sealed_payload["evidence_ids"] = list(sealed_refs)
    sealed_payload["persistence_id"] = persistence_id

    return RuntimePersistenceClosureRecord(
        persistence_id=persistence_id,
        execution_graph=canonical,
        evidence_ids=sealed_refs,
        persistence_fingerprint=_stable_fingerprint(sealed_payload),
        payload=sealed_payload,
    )


def validate_runtime_persistence_chain(
    execution_graph: RuntimePersistenceExecutionGraph | Mapping[str, Any],
    *,
    persistence_record: Mapping[str, Any],
    snapshot_record: Mapping[str, Any] | None = None,
    resume_record: Mapping[str, Any] | None = None,
    recovered_record: Mapping[str, Any] | None = None,
    evidence_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    canonical = (
        execution_graph
        if isinstance(execution_graph, RuntimePersistenceExecutionGraph)
        else RuntimePersistenceExecutionGraph.from_mapping(execution_graph)
    )
    sealed_persistence = seal_runtime_persistence(
        persistence_record,
        execution_graph=canonical,
        evidence_ids=evidence_ids,
    )

    checked = {"persistence": sealed_persistence.persistence_id}
    for label, record in (
        ("snapshot", snapshot_record),
        ("resume", resume_record),
        ("recovered", recovered_record),
    ):
        if record is None:
            continue
        sealed = seal_runtime_persistence(
            record,
            execution_graph=canonical,
            evidence_ids=sealed_persistence.evidence_ids,
        )
        fingerprint = _collect_field(record, "execution_fingerprint")
        if fingerprint and fingerprint != canonical.fingerprint:
            raise ValueError(f"runtime_persistence_{label}_fingerprint_drift")
        checked[label] = sealed.persistence_id

    return {
        "schema": RUNTIME_PERSISTENCE_CLOSURE_SCHEMA,
        "valid": True,
        "execution_graph": canonical.to_dict(),
        "execution_fingerprint": canonical.fingerprint,
        "evidence_ids": list(sealed_persistence.evidence_ids),
        "persistence_fingerprint": sealed_persistence.persistence_fingerprint,
        "checked_records": checked,
    }


__all__ = [
    "EXECUTION_GRAPH_FIELDS",
    "FORBIDDEN_SENTINEL_IDENTITIES",
    "RUNTIME_PERSISTENCE_CLOSURE_SCHEMA",
    "RuntimePersistenceClosureRecord",
    "RuntimePersistenceExecutionGraph",
    "seal_runtime_persistence",
    "validate_runtime_persistence_chain",
]

from __future__ import annotations

"""Runtime governance graph closure contract.

This passive contract binds the already-sealed runtime closure layers into one
canonical governance graph.  It does not grant authority, issue capability,
assign ownership, mutate state, write evidence, or persist data.  It validates
that every handoff preserves the same graph across authority, capability,
identity, ownership, mutation, evidence, persistence, resume, continuation, and
replan boundaries.
"""

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

RUNTIME_GOVERNANCE_GRAPH_CLOSURE_SCHEMA = "zero.runtime_governance_graph_closure.v1"

GOVERNANCE_GRAPH_FIELDS = (
    "goal_id",
    "root_goal_id",
    "source_goal_id",
    "goal_lineage_id",
    "session_id",
    "runtime_session_id",
    "execution_id",
    "authority_decision_id",
    "capability_id",
    "identity_fingerprint",
    "goal_owner",
    "session_owner",
    "execution_owner",
    "capability_owner",
    "evidence_owner",
    "persistence_owner",
    "ownership_fingerprint",
    "mutation_request_id",
    "mutation_id",
    "mutation_fingerprint",
    "evidence_id",
    "persistence_id",
)

FORBIDDEN_GOVERNANCE_SENTINELS = {
    "",
    "unknown",
    "default",
    "legacy",
    "runtime",
    "system",
    "fallback",
    "wildcard",
    "implicit",
    "unsealed",
    "parallel",
    "bypass",
    "direct",
    "governance",
    "none",
    "null",
    "undefined",
}

BYPASS_MARKER_FIELDS = (
    "parallel_governance_graph",
    "hidden_governance_source",
    "legacy_governance_path",
    "governance_bypass",
    "unsealed_governance",
    "direct_authority",
    "direct_capability",
    "direct_identity",
    "direct_ownership",
    "direct_mutation",
    "direct_evidence",
    "direct_persistence",
    "authority_bypassed",
    "capability_bypassed",
    "identity_bypassed",
    "ownership_bypassed",
    "mutation_bypassed",
    "evidence_bypassed",
    "persistence_bypassed",
    "resume_bypassed",
)

_NESTED_KEYS = (
    "governance_graph",
    "runtime_governance_graph",
    "canonical_governance_graph",
    "authority_graph",
    "capability_graph",
    "identity_graph",
    "runtime_identity_graph",
    "canonical_identity_graph",
    "ownership_graph",
    "runtime_ownership_graph",
    "mutation_graph",
    "runtime_mutation_graph",
    "evidence_graph",
    "runtime_evidence_graph",
    "persistence_graph",
    "runtime_persistence_graph",
    "resume_graph",
    "continuation_graph",
    "replan_graph",
    "metadata",
    "payload",
    "task",
    "record",
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


def _governance_subset(source: Mapping[str, Any]) -> dict[str, str]:
    return {field: _collect_field(source, field) for field in GOVERNANCE_GRAPH_FIELDS}


def _reject_forbidden(values: Mapping[str, str], *, fields: Sequence[str]) -> None:
    for field in fields:
        value = _text(values.get(field))
        if value.lower() in FORBIDDEN_GOVERNANCE_SENTINELS:
            raise ValueError(f"runtime_governance_forbidden_value:{field}")


def _require(values: Mapping[str, str], *, fields: Sequence[str], prefix: str) -> None:
    missing = [field for field in fields if not _text(values.get(field))]
    if missing:
        raise ValueError(prefix + ":" + ",".join(missing))


def _reject_bypass_markers(source: Mapping[str, Any], *, label: str) -> None:
    for field in BYPASS_MARKER_FIELDS:
        value = source.get(field)
        if value is True or _text(value).lower() in {"1", "true", "yes", "bypass", "direct", "parallel"}:
            raise ValueError(f"runtime_governance_bypass_marker:{label}:{field}")
    for key in _NESTED_KEYS:
        nested = source.get(key)
        if isinstance(nested, Mapping):
            _reject_bypass_markers(nested, label=label)


@dataclass(frozen=True)
class RuntimeGovernanceGraph:
    goal_id: str
    root_goal_id: str
    source_goal_id: str
    goal_lineage_id: str
    session_id: str
    runtime_session_id: str
    execution_id: str
    authority_decision_id: str
    capability_id: str
    identity_fingerprint: str
    goal_owner: str
    session_owner: str
    execution_owner: str
    capability_owner: str
    evidence_owner: str
    persistence_owner: str
    ownership_fingerprint: str
    mutation_request_id: str
    mutation_id: str
    mutation_fingerprint: str
    evidence_id: str
    persistence_id: str

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "RuntimeGovernanceGraph":
        graph = _governance_subset(source)
        _require(graph, fields=GOVERNANCE_GRAPH_FIELDS, prefix="runtime_governance_graph_missing")
        _reject_forbidden(graph, fields=GOVERNANCE_GRAPH_FIELDS)
        return cls(**graph)

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in GOVERNANCE_GRAPH_FIELDS}

    @property
    def fingerprint(self) -> str:
        return _stable_fingerprint(self.to_dict())


@dataclass(frozen=True)
class RuntimeGovernanceClosureRecord:
    closure_id: str
    governance_graph: RuntimeGovernanceGraph
    governance_fingerprint: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUNTIME_GOVERNANCE_GRAPH_CLOSURE_SCHEMA,
            "closure_id": self.closure_id,
            "governance_graph": self.governance_graph.to_dict(),
            "governance_fingerprint": self.governance_fingerprint,
            "payload": copy.deepcopy(self.payload),
        }


def seal_runtime_governance_graph(
    record: Mapping[str, Any],
    *,
    governance_graph: RuntimeGovernanceGraph | Mapping[str, Any],
    label: str = "record",
) -> RuntimeGovernanceClosureRecord:
    """Seal one record to the canonical governance graph.

    Existing governance fields inside the record are accepted only when they
    match the canonical graph. Missing fields are not backfilled from sentinel
    identifiers; the caller must provide the canonical graph explicitly.
    """

    canonical = (
        governance_graph
        if isinstance(governance_graph, RuntimeGovernanceGraph)
        else RuntimeGovernanceGraph.from_mapping(governance_graph)
    )
    payload = _mapping(record)
    if not payload:
        raise ValueError("runtime_governance_payload_required")
    _reject_bypass_markers(payload, label=label)

    closure_id = _collect_field(payload, "governance_closure_id") or _collect_field(payload, "closure_id")
    if not closure_id or closure_id.lower() in FORBIDDEN_GOVERNANCE_SENTINELS:
        raise ValueError("runtime_governance_closure_id_required")

    present_graph = _governance_subset(payload)
    present_fields = [field for field, value in present_graph.items() if _text(value)]
    if present_fields:
        _reject_forbidden(present_graph, fields=present_fields)
    for field, expected in canonical.to_dict().items():
        actual = _text(present_graph.get(field))
        if actual and actual != expected:
            raise ValueError(f"runtime_governance_graph_drift:{label}:{field}")

    payload_fingerprint = _collect_field(payload, "governance_fingerprint")
    if payload_fingerprint and payload_fingerprint != canonical.fingerprint:
        raise ValueError(f"runtime_governance_fingerprint_drift:{label}")

    sealed_payload = copy.deepcopy(payload)
    sealed_payload["governance_closure_id"] = closure_id
    sealed_payload["governance_graph"] = canonical.to_dict()
    sealed_payload["governance_fingerprint"] = canonical.fingerprint

    return RuntimeGovernanceClosureRecord(
        closure_id=closure_id,
        governance_graph=canonical,
        governance_fingerprint=canonical.fingerprint,
        payload=sealed_payload,
    )


def validate_runtime_governance_graph_chain(
    governance_graph: RuntimeGovernanceGraph | Mapping[str, Any],
    *,
    authority_record: Mapping[str, Any] | None = None,
    capability_record: Mapping[str, Any] | None = None,
    identity_record: Mapping[str, Any] | None = None,
    ownership_record: Mapping[str, Any] | None = None,
    mutation_record: Mapping[str, Any] | None = None,
    evidence_record: Mapping[str, Any] | None = None,
    persistence_record: Mapping[str, Any] | None = None,
    resume_record: Mapping[str, Any] | None = None,
    continuation_record: Mapping[str, Any] | None = None,
    replan_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate that all closure layers preserve one governance graph."""

    canonical = (
        governance_graph
        if isinstance(governance_graph, RuntimeGovernanceGraph)
        else RuntimeGovernanceGraph.from_mapping(governance_graph)
    )
    records = {
        "authority": authority_record,
        "capability": capability_record,
        "identity": identity_record,
        "ownership": ownership_record,
        "mutation": mutation_record,
        "evidence": evidence_record,
        "persistence": persistence_record,
        "resume": resume_record,
        "continuation": continuation_record,
        "replan": replan_record,
    }
    checked: dict[str, str] = {}
    for label, candidate in records.items():
        if candidate is None:
            continue
        sealed = seal_runtime_governance_graph(candidate, governance_graph=canonical, label=label)
        checked[label] = sealed.closure_id

    return {
        "schema": RUNTIME_GOVERNANCE_GRAPH_CLOSURE_SCHEMA,
        "valid": True,
        "governance_graph": canonical.to_dict(),
        "governance_fingerprint": canonical.fingerprint,
        "checked_records": checked,
    }


__all__ = [
    "BYPASS_MARKER_FIELDS",
    "FORBIDDEN_GOVERNANCE_SENTINELS",
    "GOVERNANCE_GRAPH_FIELDS",
    "RUNTIME_GOVERNANCE_GRAPH_CLOSURE_SCHEMA",
    "RuntimeGovernanceClosureRecord",
    "RuntimeGovernanceGraph",
    "seal_runtime_governance_graph",
    "validate_runtime_governance_graph_chain",
]

from __future__ import annotations

"""Runtime ownership closure contract.

This module seals the ownership layer above authority, capability, identity,
evidence, persistence, resume, continuation, and replan records.  It is passive:
it validates an already-declared canonical owner graph and refuses to mint,
replace, upgrade, or silently fallback to another owner.
"""

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

RUNTIME_OWNERSHIP_CLOSURE_SCHEMA = "zero.runtime_ownership_closure.v1"

OWNER_GRAPH_FIELDS = (
    "goal_owner",
    "session_owner",
    "execution_owner",
    "capability_owner",
    "evidence_owner",
    "persistence_owner",
)

IDENTITY_BINDING_FIELDS = (
    "goal_id",
    "root_goal_id",
    "source_goal_id",
    "goal_lineage_id",
    "session_id",
    "runtime_session_id",
    "execution_id",
    "authority_decision_id",
    "capability_id",
    "evidence_id",
    "persistence_id",
)

FORBIDDEN_OWNER_SENTINELS = {
    "",
    "unknown",
    "default",
    "legacy",
    "runtime",
    "system",
    "owner",
    "auto",
    "fallback",
    "none",
    "null",
    "undefined",
}

_NESTED_KEYS = (
    "ownership_graph",
    "runtime_ownership_graph",
    "canonical_ownership_graph",
    "owner_graph",
    "owners",
    "ownership",
    "identity_graph",
    "runtime_identity_graph",
    "canonical_identity_graph",
    "execution_graph",
    "runtime_execution_graph",
    "authority_graph",
    "capability_graph",
    "evidence_graph",
    "persistence_graph",
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


def _reject_forbidden(values: Mapping[str, str], *, fields: Sequence[str]) -> None:
    for field in fields:
        value = _text(values.get(field))
        if value.lower() in FORBIDDEN_OWNER_SENTINELS:
            raise ValueError(f"runtime_ownership_forbidden_owner:{field}")


def _require(values: Mapping[str, str], *, fields: Sequence[str], prefix: str) -> None:
    missing = [field for field in fields if not _text(values.get(field))]
    if missing:
        raise ValueError(prefix + ":" + ",".join(missing))


def _owner_subset(source: Mapping[str, Any]) -> dict[str, str]:
    return {field: _collect_field(source, field) for field in OWNER_GRAPH_FIELDS}


def _identity_subset(source: Mapping[str, Any]) -> dict[str, str]:
    return {field: _collect_field(source, field) for field in IDENTITY_BINDING_FIELDS}


@dataclass(frozen=True)
class RuntimeOwnershipGraph:
    goal_owner: str
    session_owner: str
    execution_owner: str
    capability_owner: str
    evidence_owner: str
    persistence_owner: str

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "RuntimeOwnershipGraph":
        graph = _owner_subset(source)
        _require(graph, fields=OWNER_GRAPH_FIELDS, prefix="runtime_ownership_graph_missing")
        _reject_forbidden(graph, fields=OWNER_GRAPH_FIELDS)
        return cls(**graph)

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in OWNER_GRAPH_FIELDS}

    @property
    def fingerprint(self) -> str:
        return _stable_fingerprint(self.to_dict())


@dataclass(frozen=True)
class RuntimeOwnershipClosureRecord:
    closure_id: str
    ownership_graph: RuntimeOwnershipGraph
    identity_binding: dict[str, str]
    owner_fingerprint: str
    identity_fingerprint: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUNTIME_OWNERSHIP_CLOSURE_SCHEMA,
            "closure_id": self.closure_id,
            "ownership_graph": self.ownership_graph.to_dict(),
            "identity_binding": copy.deepcopy(self.identity_binding),
            "owner_fingerprint": self.owner_fingerprint,
            "identity_fingerprint": self.identity_fingerprint,
            "payload": copy.deepcopy(self.payload),
        }


def seal_runtime_ownership(
    record: Mapping[str, Any],
    *,
    ownership_graph: RuntimeOwnershipGraph | Mapping[str, Any],
    identity_binding: Mapping[str, Any] | None = None,
) -> RuntimeOwnershipClosureRecord:
    """Seal a runtime record to one canonical ownership graph.

    Existing owner fields in the record are allowed only when they match the
    canonical graph.  Missing owner fields are not backfilled from fallback
    sentinels; the caller must supply the canonical owner graph explicitly.
    """

    canonical = (
        ownership_graph
        if isinstance(ownership_graph, RuntimeOwnershipGraph)
        else RuntimeOwnershipGraph.from_mapping(ownership_graph)
    )
    payload = _mapping(record)
    if not payload:
        raise ValueError("runtime_ownership_payload_required")

    closure_id = _collect_field(payload, "ownership_closure_id") or _collect_field(payload, "closure_id")
    if not closure_id or closure_id.lower() in FORBIDDEN_OWNER_SENTINELS:
        raise ValueError("runtime_ownership_closure_id_required")

    present_owners = _owner_subset(payload)
    present_fields = [field for field, value in present_owners.items() if _text(value)]
    if present_fields:
        _reject_forbidden(present_owners, fields=present_fields)
    for field, expected in canonical.to_dict().items():
        actual = _text(present_owners.get(field))
        if actual and actual != expected:
            raise ValueError(f"runtime_ownership_graph_drift:{field}")

    binding_source: Mapping[str, Any] = identity_binding or payload
    binding = _identity_subset(binding_source)
    binding = {field: value for field, value in binding.items() if _text(value)}
    if not binding:
        raise ValueError("runtime_ownership_identity_binding_required")

    sealed_payload = copy.deepcopy(payload)
    sealed_payload["ownership_closure_id"] = closure_id
    sealed_payload["ownership_graph"] = canonical.to_dict()
    sealed_payload["owner_fingerprint"] = canonical.fingerprint
    sealed_payload["identity_binding"] = copy.deepcopy(binding)
    sealed_payload["identity_fingerprint"] = _stable_fingerprint(binding)

    return RuntimeOwnershipClosureRecord(
        closure_id=closure_id,
        ownership_graph=canonical,
        identity_binding=binding,
        owner_fingerprint=canonical.fingerprint,
        identity_fingerprint=_stable_fingerprint(binding),
        payload=sealed_payload,
    )


def validate_runtime_ownership_chain(
    ownership_graph: RuntimeOwnershipGraph | Mapping[str, Any],
    *,
    identity_binding: Mapping[str, Any],
    goal_record: Mapping[str, Any] | None = None,
    session_record: Mapping[str, Any] | None = None,
    execution_record: Mapping[str, Any] | None = None,
    capability_record: Mapping[str, Any] | None = None,
    evidence_record: Mapping[str, Any] | None = None,
    persistence_record: Mapping[str, Any] | None = None,
    resume_record: Mapping[str, Any] | None = None,
    continuation_record: Mapping[str, Any] | None = None,
    replan_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate that all runtime layers preserve the same owner graph."""

    canonical = (
        ownership_graph
        if isinstance(ownership_graph, RuntimeOwnershipGraph)
        else RuntimeOwnershipGraph.from_mapping(ownership_graph)
    )
    canonical_binding = _identity_subset(identity_binding)
    canonical_binding = {field: value for field, value in canonical_binding.items() if _text(value)}
    if not canonical_binding:
        raise ValueError("runtime_ownership_identity_binding_required")

    records = {
        "goal": goal_record,
        "session": session_record,
        "execution": execution_record,
        "capability": capability_record,
        "evidence": evidence_record,
        "persistence": persistence_record,
        "resume": resume_record,
        "continuation": continuation_record,
        "replan": replan_record,
    }
    checked: dict[str, str] = {}
    owner_fp = canonical.fingerprint
    identity_fp = _stable_fingerprint(canonical_binding)

    for label, candidate in records.items():
        if candidate is None:
            continue
        sealed = seal_runtime_ownership(
            candidate,
            ownership_graph=canonical,
            identity_binding=canonical_binding,
        )
        payload_owner_fp = _collect_field(candidate, "owner_fingerprint")
        if payload_owner_fp and payload_owner_fp != owner_fp:
            raise ValueError(f"runtime_ownership_fingerprint_drift:{label}")
        payload_identity_fp = _collect_field(candidate, "identity_fingerprint")
        if payload_identity_fp and payload_identity_fp != identity_fp:
            raise ValueError(f"runtime_ownership_identity_fingerprint_drift:{label}")
        present_binding = _identity_subset(candidate)
        for field, expected in canonical_binding.items():
            actual = _text(present_binding.get(field))
            if actual and actual != expected:
                raise ValueError(f"runtime_ownership_identity_drift:{label}:{field}")
        checked[label] = sealed.closure_id

    return {
        "schema": RUNTIME_OWNERSHIP_CLOSURE_SCHEMA,
        "valid": True,
        "owner_fingerprint": owner_fp,
        "identity_fingerprint": identity_fp,
        "checked_records": checked,
        "ownership_graph": canonical.to_dict(),
        "identity_binding": canonical_binding,
    }


__all__ = [
    "FORBIDDEN_OWNER_SENTINELS",
    "IDENTITY_BINDING_FIELDS",
    "OWNER_GRAPH_FIELDS",
    "RUNTIME_OWNERSHIP_CLOSURE_SCHEMA",
    "RuntimeOwnershipClosureRecord",
    "RuntimeOwnershipGraph",
    "seal_runtime_ownership",
    "validate_runtime_ownership_chain",
]

from __future__ import annotations

"""Runtime mutation closure contract.

This passive contract closes the final mutation exit path after runtime
authority, capability, identity, evidence, persistence, and ownership have been
sealed.  It never grants permission and never performs a mutation; it validates
that a mutation request and every downstream record preserve the same canonical
mutation graph.
"""

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

RUNTIME_MUTATION_CLOSURE_SCHEMA = "zero.runtime_mutation_closure.v1"

MUTATION_GRAPH_FIELDS = (
    "mutation_request_id",
    "mutation_id",
    "authority_decision_id",
    "capability_id",
    "execution_id",
    "identity_fingerprint",
    "ownership_fingerprint",
    "evidence_id",
    "persistence_id",
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

OWNER_GRAPH_FIELDS = (
    "goal_owner",
    "session_owner",
    "execution_owner",
    "capability_owner",
    "evidence_owner",
    "persistence_owner",
)

FORBIDDEN_MUTATION_SENTINELS = {
    "",
    "unknown",
    "default",
    "legacy",
    "runtime",
    "system",
    "mutation",
    "direct",
    "bypass",
    "fallback",
    "wildcard",
    "unsealed",
    "implicit",
    "none",
    "null",
    "undefined",
}

BYPASS_MARKER_FIELDS = (
    "direct_mutation",
    "ungoverned_mutation",
    "mutation_bypass",
    "authority_bypassed",
    "capability_bypassed",
    "identity_bypassed",
    "ownership_bypassed",
    "evidence_bypassed",
    "persistence_bypassed",
)

_NESTED_KEYS = (
    "mutation_graph",
    "runtime_mutation_graph",
    "canonical_mutation_graph",
    "mutation_request",
    "mutation_record",
    "authority_graph",
    "capability_graph",
    "identity_graph",
    "runtime_identity_graph",
    "canonical_identity_graph",
    "ownership_graph",
    "runtime_ownership_graph",
    "evidence_graph",
    "persistence_graph",
    "resume_graph",
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
        if value.lower() in FORBIDDEN_MUTATION_SENTINELS:
            raise ValueError(f"runtime_mutation_forbidden_value:{field}")


def _require(values: Mapping[str, str], *, fields: Sequence[str], prefix: str) -> None:
    missing = [field for field in fields if not _text(values.get(field))]
    if missing:
        raise ValueError(prefix + ":" + ",".join(missing))


def _mutation_subset(source: Mapping[str, Any]) -> dict[str, str]:
    return {field: _collect_field(source, field) for field in MUTATION_GRAPH_FIELDS}


def _identity_subset(source: Mapping[str, Any]) -> dict[str, str]:
    return {field: _collect_field(source, field) for field in IDENTITY_BINDING_FIELDS}


def _owner_subset(source: Mapping[str, Any]) -> dict[str, str]:
    return {field: _collect_field(source, field) for field in OWNER_GRAPH_FIELDS}


def _reject_bypass_markers(source: Mapping[str, Any], *, label: str) -> None:
    for field in BYPASS_MARKER_FIELDS:
        value = source.get(field)
        if value is True or _text(value).lower() in {"1", "true", "yes", "bypass", "direct"}:
            raise ValueError(f"runtime_mutation_bypass_marker:{label}:{field}")
    for key in _NESTED_KEYS:
        nested = source.get(key)
        if isinstance(nested, Mapping):
            _reject_bypass_markers(nested, label=label)


@dataclass(frozen=True)
class RuntimeMutationGraph:
    mutation_request_id: str
    mutation_id: str
    authority_decision_id: str
    capability_id: str
    execution_id: str
    identity_fingerprint: str
    ownership_fingerprint: str
    evidence_id: str
    persistence_id: str

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "RuntimeMutationGraph":
        graph = _mutation_subset(source)
        _require(graph, fields=MUTATION_GRAPH_FIELDS, prefix="runtime_mutation_graph_missing")
        _reject_forbidden(graph, fields=MUTATION_GRAPH_FIELDS)
        return cls(**graph)

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in MUTATION_GRAPH_FIELDS}

    @property
    def fingerprint(self) -> str:
        return _stable_fingerprint(self.to_dict())


@dataclass(frozen=True)
class RuntimeMutationClosureRecord:
    closure_id: str
    mutation_graph: RuntimeMutationGraph
    mutation_fingerprint: str
    identity_binding: dict[str, str]
    ownership_graph: dict[str, str]
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RUNTIME_MUTATION_CLOSURE_SCHEMA,
            "closure_id": self.closure_id,
            "mutation_graph": self.mutation_graph.to_dict(),
            "mutation_fingerprint": self.mutation_fingerprint,
            "identity_binding": copy.deepcopy(self.identity_binding),
            "ownership_graph": copy.deepcopy(self.ownership_graph),
            "payload": copy.deepcopy(self.payload),
        }


def seal_runtime_mutation(
    record: Mapping[str, Any],
    *,
    mutation_graph: RuntimeMutationGraph | Mapping[str, Any],
    identity_binding: Mapping[str, Any],
    ownership_graph: Mapping[str, Any],
) -> RuntimeMutationClosureRecord:
    """Seal one record to the canonical mutation graph.

    The caller must provide the already-authorized graph.  Existing mutation
    fields inside the record are accepted only when they match that graph.
    """

    canonical = (
        mutation_graph
        if isinstance(mutation_graph, RuntimeMutationGraph)
        else RuntimeMutationGraph.from_mapping(mutation_graph)
    )
    payload = _mapping(record)
    if not payload:
        raise ValueError("runtime_mutation_payload_required")
    _reject_bypass_markers(payload, label="record")

    closure_id = _collect_field(payload, "mutation_closure_id") or _collect_field(payload, "closure_id")
    if not closure_id or closure_id.lower() in FORBIDDEN_MUTATION_SENTINELS:
        raise ValueError("runtime_mutation_closure_id_required")

    present_mutation = _mutation_subset(payload)
    present_fields = [field for field, value in present_mutation.items() if _text(value)]
    if present_fields:
        _reject_forbidden(present_mutation, fields=present_fields)
    for field, expected in canonical.to_dict().items():
        actual = _text(present_mutation.get(field))
        if actual and actual != expected:
            raise ValueError(f"runtime_mutation_graph_drift:{field}")

    binding = _identity_subset(identity_binding)
    binding = {field: value for field, value in binding.items() if _text(value)}
    if not binding:
        raise ValueError("runtime_mutation_identity_binding_required")
    owners = _owner_subset(ownership_graph)
    owners = {field: value for field, value in owners.items() if _text(value)}
    if not owners:
        raise ValueError("runtime_mutation_ownership_graph_required")

    if binding.get("execution_id") and binding["execution_id"] != canonical.execution_id:
        raise ValueError("runtime_mutation_identity_drift:execution_id")
    if binding.get("authority_decision_id") and binding["authority_decision_id"] != canonical.authority_decision_id:
        raise ValueError("runtime_mutation_identity_drift:authority_decision_id")
    if binding.get("capability_id") and binding["capability_id"] != canonical.capability_id:
        raise ValueError("runtime_mutation_identity_drift:capability_id")
    if binding.get("evidence_id") and binding["evidence_id"] != canonical.evidence_id:
        raise ValueError("runtime_mutation_identity_drift:evidence_id")
    if binding.get("persistence_id") and binding["persistence_id"] != canonical.persistence_id:
        raise ValueError("runtime_mutation_identity_drift:persistence_id")

    sealed_payload = copy.deepcopy(payload)
    sealed_payload["mutation_closure_id"] = closure_id
    sealed_payload["mutation_graph"] = canonical.to_dict()
    sealed_payload["mutation_fingerprint"] = canonical.fingerprint
    sealed_payload["identity_binding"] = copy.deepcopy(binding)
    sealed_payload["ownership_graph"] = copy.deepcopy(owners)

    return RuntimeMutationClosureRecord(
        closure_id=closure_id,
        mutation_graph=canonical,
        mutation_fingerprint=canonical.fingerprint,
        identity_binding=binding,
        ownership_graph=owners,
        payload=sealed_payload,
    )


def validate_runtime_mutation_chain(
    mutation_graph: RuntimeMutationGraph | Mapping[str, Any],
    *,
    identity_binding: Mapping[str, Any],
    ownership_graph: Mapping[str, Any],
    request_record: Mapping[str, Any] | None = None,
    authority_record: Mapping[str, Any] | None = None,
    capability_record: Mapping[str, Any] | None = None,
    identity_record: Mapping[str, Any] | None = None,
    ownership_record: Mapping[str, Any] | None = None,
    mutation_record: Mapping[str, Any] | None = None,
    evidence_record: Mapping[str, Any] | None = None,
    persistence_record: Mapping[str, Any] | None = None,
    resume_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate that a mutation path remains closed across all layers."""

    canonical = (
        mutation_graph
        if isinstance(mutation_graph, RuntimeMutationGraph)
        else RuntimeMutationGraph.from_mapping(mutation_graph)
    )
    identity_fp = _stable_fingerprint(_identity_subset(identity_binding))
    owner_fp = _stable_fingerprint(_owner_subset(ownership_graph))
    if identity_fp != canonical.identity_fingerprint:
        raise ValueError("runtime_mutation_identity_fingerprint_drift:canonical")
    if owner_fp != canonical.ownership_fingerprint:
        raise ValueError("runtime_mutation_ownership_fingerprint_drift:canonical")

    records = {
        "request": request_record,
        "authority": authority_record,
        "capability": capability_record,
        "identity": identity_record,
        "ownership": ownership_record,
        "mutation": mutation_record,
        "evidence": evidence_record,
        "persistence": persistence_record,
        "resume": resume_record,
    }
    checked: dict[str, str] = {}
    mutation_fp = canonical.fingerprint

    for label, candidate in records.items():
        if candidate is None:
            continue
        _reject_bypass_markers(candidate, label=label)
        sealed = seal_runtime_mutation(
            candidate,
            mutation_graph=canonical,
            identity_binding=identity_binding,
            ownership_graph=ownership_graph,
        )
        payload_mutation_fp = _collect_field(candidate, "mutation_fingerprint")
        if payload_mutation_fp and payload_mutation_fp != mutation_fp:
            raise ValueError(f"runtime_mutation_fingerprint_drift:{label}")
        present_identity = _identity_subset(candidate)
        for field, expected in _identity_subset(identity_binding).items():
            actual = _text(present_identity.get(field))
            if actual and expected and actual != expected:
                raise ValueError(f"runtime_mutation_identity_drift:{label}:{field}")
        checked[label] = sealed.closure_id

    return {
        "schema": RUNTIME_MUTATION_CLOSURE_SCHEMA,
        "valid": True,
        "mutation_fingerprint": mutation_fp,
        "checked_records": checked,
        "mutation_graph": canonical.to_dict(),
        "identity_fingerprint": identity_fp,
        "ownership_fingerprint": owner_fp,
    }


__all__ = [
    "BYPASS_MARKER_FIELDS",
    "FORBIDDEN_MUTATION_SENTINELS",
    "IDENTITY_BINDING_FIELDS",
    "MUTATION_GRAPH_FIELDS",
    "OWNER_GRAPH_FIELDS",
    "RUNTIME_MUTATION_CLOSURE_SCHEMA",
    "RuntimeMutationClosureRecord",
    "RuntimeMutationGraph",
    "seal_runtime_mutation",
    "validate_runtime_mutation_chain",
]

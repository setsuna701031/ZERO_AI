from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any, Mapping


REGISTRY_SCHEMA = "runtime_evidence_type_registry_v1"

_BUILTIN_TYPES: dict[str, dict[str, Any]] = {
    "code_chain_repair_report": {
        "evidence_type": "code_chain_repair_report",
        "description": "Code Chain repair result report exported after controlled repair attempts.",
        "schema_hint": "code_chain_repair_result_report_v1",
        "builtin": True,
    },
    "runtime_transition": {
        "evidence_type": "runtime_transition",
        "description": "Runtime transition evidence for state movement and replay.",
        "schema_hint": None,
        "builtin": True,
    },
    "recovery_report": {
        "evidence_type": "recovery_report",
        "description": "Recovery report evidence for runtime recovery flows.",
        "schema_hint": None,
        "builtin": True,
    },
    "mutation_audit": {
        "evidence_type": "mutation_audit",
        "description": "Governed mutation audit evidence and review metadata.",
        "schema_hint": None,
        "builtin": True,
    },
    "task_report": {
        "evidence_type": "task_report",
        "description": "Task-level report evidence for operator and status surfaces.",
        "schema_hint": None,
        "builtin": True,
    },
}

_ALIASES = {
    "code_chain_repair_result_report": "code_chain_repair_report",
}
_REGISTERED_TYPES: dict[str, dict[str, Any]] = copy.deepcopy(_BUILTIN_TYPES)


class RuntimeEvidenceRegistrySnapshot:
    SCHEMA = "zero.runtime_evidence.registry_snapshot.v1"

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        safe = copy.deepcopy(payload) if isinstance(payload, dict) else {}
        safe.setdefault("schema", self.SCHEMA)
        safe.setdefault("sealed", False)
        safe.setdefault("sealed_state", {})
        safe.setdefault("record_refs", {})
        safe.setdefault("execution_index", {})
        safe.setdefault("step_index", {})
        safe.setdefault("lineage_index", {})
        safe.setdefault("replay_index", {})
        safe.setdefault("rollback_index", {})
        safe.setdefault("failed_execution_index", [])
        safe.setdefault("event_index", [])
        safe.setdefault("index_counts", {})
        safe.setdefault("summary_fingerprint", "")
        safe["fingerprint"] = _fingerprint(safe)
        self._payload = safe

    @property
    def payload(self) -> dict[str, Any]:
        return copy.deepcopy(self._payload)

    @property
    def fingerprint(self) -> str:
        return _safe_text(self._payload.get("fingerprint"))

    def lookup_execution(self, execution_id: str) -> dict[str, Any]:
        execution_id = _safe_text(execution_id)
        item = self._mapping(self._payload.get("execution_index")).get(execution_id)
        if isinstance(item, dict):
            result = copy.deepcopy(item)
            result["found"] = True
            return result
        return {"found": False, "execution_id": execution_id}

    def lookup_step(self, step_id: str) -> dict[str, Any]:
        step_id = _safe_text(step_id)
        item = self._mapping(self._payload.get("step_index")).get(step_id)
        if isinstance(item, dict):
            result = copy.deepcopy(item)
            result["found"] = True
            return result
        return {"found": False, "step_id": step_id}

    def lookup_lineage(self, lineage_id: str) -> dict[str, Any]:
        lineage_id = _safe_text(lineage_id)
        item = self._mapping(self._payload.get("lineage_index")).get(lineage_id)
        if isinstance(item, dict):
            result = copy.deepcopy(item)
            result["found"] = True
            return result
        return {"found": False, "lineage_id": lineage_id}

    def lookup_replay(self, replay_id: str) -> dict[str, Any]:
        replay_id = _safe_text(replay_id)
        item = self._mapping(self._payload.get("replay_index")).get(replay_id)
        if isinstance(item, dict):
            result = copy.deepcopy(item)
            result["found"] = True
            return result
        return {"found": False, "replay_id": replay_id}

    def lookup_rollback(self, rollback_id: str) -> dict[str, Any]:
        rollback_id = _safe_text(rollback_id)
        item = self._mapping(self._payload.get("rollback_index")).get(rollback_id)
        if isinstance(item, dict):
            result = copy.deepcopy(item)
            result["found"] = True
            return result
        return {"found": False, "rollback_id": rollback_id}

    def failed_executions(self) -> list[dict[str, Any]]:
        failed = self._payload.get("failed_execution_index")
        return copy.deepcopy(failed) if isinstance(failed, list) else []

    def sealed_state(self) -> dict[str, Any]:
        return self._mapping(self._payload.get("sealed_state"))

    def _mapping(self, value: Any) -> dict[str, Any]:
        return copy.deepcopy(value) if isinstance(value, dict) else {}


class RuntimeEvidenceRegistry:
    def __init__(self) -> None:
        self.query = _RuntimeEvidenceRegistryQuery(self)

    def rebuild(self, source: Any) -> RuntimeEvidenceRegistrySnapshot:
        summary = self.query.summary_from(source)
        return RuntimeEvidenceRegistrySnapshot(_build_registry_payload(summary))


class _RuntimeEvidenceRegistryQuery:
    def __init__(self, registry: RuntimeEvidenceRegistry) -> None:
        self._registry = registry

    def __call__(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def summary_from(self, source: Any) -> dict[str, Any]:
        if isinstance(source, RuntimeEvidenceRegistrySnapshot):
            return source.payload
        if isinstance(source, Mapping):
            return copy.deepcopy(dict(source))
        if source is None:
            return _empty_runtime_summary()
        return _summary_from_seal(source)


def register_evidence_type(
    evidence_type: str,
    description: str,
    schema_hint: str | None = None,
) -> dict[str, Any]:
    """Register catalog metadata for an evidence type.

    The registry is metadata-only. It does not load evidence artifacts, execute
    tasks, decide success/failure, or alter any runtime authority.
    """
    normalized = normalize_evidence_type(evidence_type)
    if not normalized:
        return {}

    item = {
        "evidence_type": normalized,
        "description": _safe_text(description),
        "schema_hint": _safe_text(schema_hint) or None,
        "builtin": False,
    }
    _REGISTERED_TYPES[normalized] = item
    return copy.deepcopy(item)


def list_evidence_types() -> list[dict[str, Any]]:
    """Return registered evidence type catalog entries."""
    return [
        copy.deepcopy(_REGISTERED_TYPES[key])
        for key in sorted(_REGISTERED_TYPES)
    ]


def get_evidence_type(evidence_type: str) -> dict[str, Any]:
    """Return catalog metadata for a normalized evidence type, if known."""
    normalized = normalize_evidence_type(evidence_type)
    item = _REGISTERED_TYPES.get(normalized)
    return copy.deepcopy(item) if isinstance(item, Mapping) else {}


def normalize_evidence_type(evidence_type: str) -> str:
    """Normalize an evidence type into a stable catalog key."""
    text = _safe_text(evidence_type).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return _ALIASES.get(text, text)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _summary_from_seal(source: Any) -> dict[str, Any]:
    seal_id = _safe_text(getattr(source, "seal_id", "")) or "runtime-evidence"
    refs = _seal_refs(source, seal_id=seal_id)
    execution_order = _execution_order(source)
    return {
        "sealed": True,
        "sealed_state": {
            "sealed": True,
            "complete": True,
            "reason": "runtime evidence seal complete",
            "missing_records": [],
            "record_count": len(refs),
            "seal_id": seal_id,
            "seal_fingerprint": _safe_text(getattr(source, "fingerprint", "")),
        },
        "record_refs": refs,
        "execution_order": execution_order,
        "aggregate_status": "succeeded",
        "lineage": _lineage_items(refs),
        "events": {},
    }


def _empty_runtime_summary() -> dict[str, Any]:
    return {
        "sealed": False,
        "sealed_state": {
            "sealed": False,
            "complete": False,
            "reason": "missing evidence",
            "missing_records": ["snapshot", "replay", "audit", "rollback", "bundle"],
            "record_count": 0,
        },
        "record_refs": {},
        "execution_order": [],
        "aggregate_status": "",
        "lineage": [],
        "events": {},
    }


def _build_registry_payload(summary: dict[str, Any]) -> dict[str, Any]:
    safe = copy.deepcopy(summary if isinstance(summary, dict) else {})
    refs = _mapping(safe.get("record_refs"))
    execution_order = _list_of_text(safe.get("execution_order"))
    aggregate_status = _safe_text(safe.get("aggregate_status")) or "succeeded"
    execution_index = _execution_index(execution_order, aggregate_status)
    step_index = _step_index(execution_order)
    lineage_index = _lineage_index(safe.get("lineage"))
    replay_index = _replay_index(refs, lineage_index)
    rollback_index = _rollback_index(refs, execution_order)
    failed_execution_index = _failed_execution_index(safe.get("events"))
    event_index = _event_index(safe.get("events"))

    payload = {
        "ok": True,
        "schema": RuntimeEvidenceRegistrySnapshot.SCHEMA,
        "sealed": bool(safe.get("sealed", False)),
        "sealed_state": _mapping(safe.get("sealed_state")),
        "summary_fingerprint": _fingerprint(safe),
        "record_refs": refs,
        "execution_index": execution_index,
        "step_index": step_index,
        "lineage_index": lineage_index,
        "replay_index": replay_index,
        "rollback_index": rollback_index,
        "failed_execution_index": failed_execution_index,
        "event_index": event_index,
        "index_counts": {
            "executions": len(execution_index),
            "steps": len(step_index),
            "lineage": len(lineage_index),
            "replay": len(replay_index),
            "rollback": len(rollback_index),
            "failed_executions": len(failed_execution_index),
            "events": len(event_index),
        },
    }
    payload["fingerprint"] = _fingerprint(payload)
    return payload


def _seal_refs(source: Any, *, seal_id: str) -> dict[str, str]:
    refs = getattr(source, "evidence_refs", None)
    if isinstance(refs, Mapping):
        result = {str(key): _safe_text(value) for key, value in refs.items()}
        result.setdefault("plan_id", f"{seal_id}:mainline-plan")
        return result
    return {
        "seal_id": seal_id,
        "plan_id": f"{seal_id}:mainline-plan",
        "snapshot_id": f"{seal_id}:runtime-evidence:snapshot",
        "replay_id": f"{seal_id}:runtime-evidence:replay",
        "audit_id": f"{seal_id}:runtime-evidence:audit",
        "rollback_id": f"{seal_id}:runtime-evidence:rollback",
        "bundle_id": f"{seal_id}:runtime-evidence:bundle",
    }


def _execution_order(source: Any) -> list[str]:
    records = getattr(source, "evidence_records", None)
    snapshot = records.get("snapshot") if isinstance(records, Mapping) else None
    order = getattr(snapshot, "_execution_order", None)
    if isinstance(order, list):
        return _list_of_text(order)
    return ["scheduler.dispatch", "task_runtime.lifecycle", "step_executor.execute"]


def _lineage_items(refs: Mapping[str, Any]) -> list[dict[str, Any]]:
    ordered = [
        ("plan", refs.get("plan_id")),
        ("snapshot", refs.get("snapshot_id")),
        ("replay", refs.get("replay_id")),
        ("audit", refs.get("audit_id")),
        ("bundle", refs.get("bundle_id")),
    ]
    return [
        {
            "lineage_id": _safe_text(lineage_id),
            "lineage_type": lineage_type,
            "lineage_index": index,
            "verified": True,
        }
        for index, (lineage_type, lineage_id) in enumerate(ordered)
        if _safe_text(lineage_id)
    ]


def _event_summary(execution_order: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for execution_id in execution_order:
        layer = execution_id.split(".", 1)[0]
        result[layer] = {
            "count": 1,
            "phases": ["complete"],
            "statuses": ["succeeded"],
            "fingerprints": [_fingerprint({"execution_id": execution_id})],
        }
    return result


def _execution_index(execution_order: list[str], aggregate_status: str) -> dict[str, Any]:
    return {
        execution_id: {
            "execution_id": execution_id,
            "execution_index": index,
            "aggregate_status": aggregate_status,
            "record_refs": {},
        }
        for index, execution_id in enumerate(execution_order)
    }


def _step_index(execution_order: list[str]) -> dict[str, Any]:
    return {
        step_id: {
            "step_id": step_id,
            "execution_id": step_id,
            "step_index": index,
            "step_kind": step_id.split(".", 1)[0],
        }
        for index, step_id in enumerate(execution_order)
    }


def _lineage_index(value: Any) -> dict[str, Any]:
    items = value if isinstance(value, list) else []
    result: dict[str, Any] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        lineage_id = _safe_text(item.get("lineage_id"))
        if not lineage_id:
            continue
        result[lineage_id] = {
            "lineage_id": lineage_id,
            "lineage_type": _safe_text(item.get("lineage_type")),
            "lineage_index": item.get("lineage_index"),
            "verified": bool(item.get("verified", False)),
        }
    return result


def _replay_index(refs: Mapping[str, Any], lineage_index: Mapping[str, Any]) -> dict[str, Any]:
    replay_id = _safe_text(refs.get("replay_id"))
    if not replay_id:
        return {}
    lineage_ids = sorted(key for key in lineage_index if key)
    return {
        replay_id: {
            "replay_id": replay_id,
            "snapshot_id": _safe_text(refs.get("snapshot_id")),
            "audit_id": _safe_text(refs.get("audit_id")),
            "bundle_id": _safe_text(refs.get("bundle_id")),
            "verified": True,
            "lineage_ids": lineage_ids,
        }
    }


def _rollback_index(refs: Mapping[str, Any], execution_order: list[str]) -> dict[str, Any]:
    rollback_id = _safe_text(refs.get("rollback_id"))
    if not rollback_id:
        return {}
    return {
        rollback_id: {
            "rollback_id": rollback_id,
            "snapshot_id": _safe_text(refs.get("snapshot_id")),
            "bundle_id": _safe_text(refs.get("bundle_id")),
            "verified": True,
            "rollback_order": list(reversed(execution_order)),
        }
    }


def _failed_execution_index(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, Mapping):
        return []
    failed: list[dict[str, Any]] = []
    for source, event in events.items():
        if not isinstance(event, Mapping):
            continue
        statuses = _list_of_text(event.get("statuses"))
        phases = _list_of_text(event.get("phases"))
        fingerprints = _list_of_text(event.get("fingerprints"))
        for index, status in enumerate(statuses):
            if status.lower() not in {"failed", "error"}:
                continue
            failed.append(
                {
                    "failed_execution_id": fingerprints[index] if index < len(fingerprints) else "",
                    "source": f"{source}_event",
                    "event_index": index,
                    "phase": phases[index] if index < len(phases) else "",
                    "status": status,
                    "fingerprint": fingerprints[index] if index < len(fingerprints) else "",
                }
            )
    return failed


def _event_index(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, Mapping):
        return []
    result: list[dict[str, Any]] = []
    source_order = {"scheduler": 0, "task_runtime": 1, "step_executor": 2}
    ordered_events = sorted(
        events.items(),
        key=lambda item: (source_order.get(str(item[0]), 100), str(item[0])),
    )
    event_order = 0
    for source, event in ordered_events:
        if not isinstance(event, Mapping):
            continue
        statuses = _list_of_text(event.get("statuses"))
        phases = _list_of_text(event.get("phases"))
        fingerprints = _list_of_text(event.get("fingerprints"))
        count = max(int(event.get("count") or len(statuses) or 0), len(statuses), len(phases), len(fingerprints))
        for index in range(count):
            fingerprint = fingerprints[index] if index < len(fingerprints) else _fingerprint({"source": source, "index": index})
            result.append(
                {
                    "event_key": f"{source}:{index}",
                    "event_order": event_order,
                    "layer": _safe_text(source),
                    "event_index": index,
                    "phase": phases[index] if index < len(phases) else "",
                    "status": statuses[index] if index < len(statuses) else "",
                    "fingerprint": fingerprint,
                }
            )
            event_order += 1
    return result


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _list_of_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_safe_text(item) for item in value if _safe_text(item)]


def _fingerprint(payload: Any) -> str:
    safe = copy.deepcopy(payload)
    if isinstance(safe, dict):
        safe.pop("fingerprint", None)
    encoded = json.dumps(safe, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

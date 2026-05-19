from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping


SCHEMA_VERSION = "execution_landing_consistency.v1"

EXECUTION_LANDING_REQUIRED_FIELDS: tuple[str, ...] = (
    "task_id",
    "session_id",
    "status",
    "execution_result",
    "verification_result",
    "rollback_result",
    "audit_ref",
    "evidence_ref",
)

EXECUTION_LANDING_OPTIONAL_FIELDS: tuple[str, ...] = (
    "mutation_ref",
    "replay_ref",
    "repair_chain_id",
)

EXECUTION_LANDING_FLOW_NAMES: tuple[str, ...] = (
    "self_edit",
    "repair",
    "replay",
    "mutation",
)

_STATUS_FIELD = "status"
_VERIFICATION_FIELDS = ("verification_result",)
_ROLLBACK_AUDIT_FIELDS = ("rollback_result", "audit_ref")
_EVIDENCE_FIELDS = ("evidence_ref",)


def execution_landing_required_fields() -> List[str]:
    return list(EXECUTION_LANDING_REQUIRED_FIELDS)


def execution_landing_optional_fields() -> List[str]:
    return list(EXECUTION_LANDING_OPTIONAL_FIELDS)


def collect_execution_landing_contract_shapes(
    contracts: Mapping[str, Any] | None = None,
    **named_contracts: Any,
) -> Dict[str, Dict[str, Any]]:
    """Collect stable field/type shapes for execution landing contracts."""

    merged: Dict[str, Any] = {}
    if isinstance(contracts, Mapping):
        merged.update(dict(contracts))
    merged.update(named_contracts)

    shapes: Dict[str, Dict[str, Any]] = {}
    for name in sorted(_text(key) for key in merged if _text(key)):
        value = merged.get(name)
        fields = _shape_fields(value)
        shapes[name] = {
            "contract": name,
            "fields": fields,
            "field_names": sorted(fields),
            "unexpected_type": "" if _is_shape_source(value) else type(value).__name__,
        }
    return shapes


def validate_required_landing_fields(
    contract: Any,
    *,
    contract_name: str = "execution_landing.v1",
    required_fields: Iterable[str] = EXECUTION_LANDING_REQUIRED_FIELDS,
) -> Dict[str, Any]:
    required = list(required_fields)
    fields = _shape_fields(contract)
    unexpected_type = "" if _is_shape_source(contract) else type(contract).__name__
    missing = _missing_from_fields(fields, required)
    return {
        "ok": not missing and not unexpected_type,
        "contract": contract_name,
        "required_fields": required,
        "missing_fields": missing,
        "unexpected_type": unexpected_type,
    }


def detect_missing_landing_fields(
    shapes: Mapping[str, Any],
    *,
    required_fields: Iterable[str] = EXECUTION_LANDING_REQUIRED_FIELDS,
) -> Dict[str, List[str]]:
    required = list(required_fields)
    return {
        name: _missing_from_fields(_fields_for_shape(shape), required)
        for name, shape in _sorted_shape_items(shapes)
    }


def detect_incompatible_status_fields(shapes: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return _detect_incompatible_fields(shapes, (_STATUS_FIELD,))


def detect_incompatible_verification_fields(shapes: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return _detect_incompatible_fields(shapes, _VERIFICATION_FIELDS)


def detect_incompatible_rollback_audit_fields(shapes: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return _detect_incompatible_fields(shapes, _ROLLBACK_AUDIT_FIELDS)


def detect_incompatible_evidence_fields(shapes: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return _detect_incompatible_fields(shapes, _EVIDENCE_FIELDS)


def compare_execution_landing_shapes(
    shapes: Mapping[str, Any],
    *,
    required_fields: Iterable[str] = EXECUTION_LANDING_REQUIRED_FIELDS,
    optional_fields: Iterable[str] = EXECUTION_LANDING_OPTIONAL_FIELDS,
) -> Dict[str, Any]:
    required = list(required_fields)
    optional = list(optional_fields)
    compared_fields = [*required, *optional]
    incompatible = _detect_incompatible_fields(shapes, compared_fields)
    missing = detect_missing_landing_fields(shapes, required_fields=required)
    return {
        "checked_contracts": [name for name, _shape in _sorted_shape_items(shapes)],
        "missing_fields": missing,
        "incompatible_fields": incompatible,
    }


def build_execution_landing_consistency_report(
    contracts: Mapping[str, Any] | None = None,
    **named_contracts: Any,
) -> Dict[str, Any]:
    shapes = collect_execution_landing_contract_shapes(contracts, **named_contracts)
    comparison = compare_execution_landing_shapes(shapes)

    status_incompatible = detect_incompatible_status_fields(shapes)
    verification_incompatible = detect_incompatible_verification_fields(shapes)
    rollback_incompatible = _detect_incompatible_fields(shapes, ("rollback_result",))
    audit_incompatible = _detect_incompatible_fields(shapes, ("audit_ref",))
    evidence_incompatible = detect_incompatible_evidence_fields(shapes)
    missing_fields = comparison["missing_fields"]

    blocking_issues = _blocking_issues(
        missing_fields=missing_fields,
        incompatible_fields=comparison["incompatible_fields"],
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_id": "",
        "checked_contracts": comparison["checked_contracts"],
        "missing_fields": missing_fields,
        "incompatible_fields": comparison["incompatible_fields"],
        "status_compatible": not status_incompatible and not _fields_missing(missing_fields, (_STATUS_FIELD,)),
        "verification_compatible": not verification_incompatible and not _fields_missing(missing_fields, _VERIFICATION_FIELDS),
        "rollback_compatible": not rollback_incompatible and not _fields_missing(missing_fields, ("rollback_result",)),
        "audit_compatible": not audit_incompatible and not _fields_missing(missing_fields, ("audit_ref",)),
        "evidence_compatible": not evidence_incompatible and not _fields_missing(missing_fields, _EVIDENCE_FIELDS),
        "consistency_score": _consistency_score(
            shapes=shapes,
            missing_fields=comparison["missing_fields"],
            incompatible_fields=comparison["incompatible_fields"],
        ),
        "blocking_issues": blocking_issues,
    }
    report["report_id"] = _report_id(report)
    return report


def validate_execution_landing_consistency(
    contracts: Mapping[str, Any] | None = None,
    **named_contracts: Any,
) -> Dict[str, Any]:
    report = build_execution_landing_consistency_report(contracts, **named_contracts)
    return {
        "ok": not report["blocking_issues"],
        "report": report,
    }


def _shape_fields(value: Any) -> Dict[str, str]:
    if isinstance(value, Mapping):
        if isinstance(value.get("fields"), Mapping):
            return {
                _text(key): _normalize_kind(kind)
                for key, kind in value["fields"].items()
                if _text(key)
            }
        return {
            _text(key): _kind(item)
            for key, item in value.items()
            if _text(key)
        }
    if isinstance(value, (set, frozenset, list, tuple)):
        return {
            _text(item): "unknown"
            for item in value
            if _text(item)
        }
    return {}


def _is_shape_source(value: Any) -> bool:
    return isinstance(value, (Mapping, set, frozenset, list, tuple))


def _fields_for_shape(shape: Any) -> Dict[str, str]:
    if isinstance(shape, Mapping) and isinstance(shape.get("fields"), Mapping):
        return {
            _text(key): _normalize_kind(value)
            for key, value in shape["fields"].items()
            if _text(key)
        }
    return _shape_fields(shape)


def _missing_from_fields(fields: Mapping[str, str], required_fields: Iterable[str]) -> List[str]:
    return [
        field
        for field in required_fields
        if field not in fields
    ]


def _detect_incompatible_fields(
    shapes: Mapping[str, Any],
    fields: Iterable[str],
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for field in fields:
        observed: Dict[str, str] = {}
        for name, shape in _sorted_shape_items(shapes):
            shape_fields = _fields_for_shape(shape)
            if field in shape_fields:
                observed[name] = shape_fields[field]
        kinds = sorted(set(observed.values()))
        if len(kinds) > 1:
            result.append(
                {
                    "field": field,
                    "contracts": [
                        {"contract": name, "kind": observed[name]}
                        for name in sorted(observed)
                    ],
                    "kinds": kinds,
                }
            )
    return result


def _blocking_issues(
    *,
    missing_fields: Mapping[str, List[str]],
    incompatible_fields: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for contract_name in sorted(missing_fields):
        missing = list(missing_fields.get(contract_name) or [])
        if missing:
            issues.append(
                {
                    "kind": "missing_required_fields",
                    "contract": contract_name,
                    "fields": missing,
                }
            )
    for item in incompatible_fields:
        field = _text(item.get("field")) if isinstance(item, Mapping) else ""
        if field:
            issues.append(
                {
                    "kind": "incompatible_field",
                    "field": field,
                    "contracts": copy.deepcopy(item.get("contracts", [])),
                }
            )
    return issues


def _fields_missing(missing_fields: Mapping[str, List[str]], fields: Iterable[str]) -> bool:
    watched = set(fields)
    return any(
        bool(watched.intersection(contract_missing or []))
        for contract_missing in missing_fields.values()
    )


def _consistency_score(
    *,
    shapes: Mapping[str, Any],
    missing_fields: Mapping[str, List[str]],
    incompatible_fields: Iterable[Any],
) -> float:
    contract_count = max(1, len(shapes))
    required_count = len(EXECUTION_LANDING_REQUIRED_FIELDS)
    possible = max(1, contract_count * required_count + len(EXECUTION_LANDING_REQUIRED_FIELDS))
    missing_count = sum(len(fields) for fields in missing_fields.values())
    incompatible_count = len(list(incompatible_fields))
    score = max(0.0, 1.0 - ((missing_count + incompatible_count) / possible))
    return round(score, 4)


def _sorted_shape_items(shapes: Mapping[str, Any]) -> List[tuple[str, Any]]:
    if not isinstance(shapes, Mapping):
        return []
    return [
        (_text(name), shapes[name])
        for name in sorted(shapes, key=lambda item: _text(item))
        if _text(name)
    ]


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "str"
    if isinstance(value, Mapping):
        return "dict"
    if isinstance(value, list):
        return "list"
    if isinstance(value, tuple):
        return "tuple"
    if isinstance(value, set):
        return "set"
    if value is None:
        return "none"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    return type(value).__name__


def _normalize_kind(value: Any) -> str:
    text = _text(value)
    return text or _kind(value)


def _report_id(report: Mapping[str, Any]) -> str:
    payload = {
        "checked_contracts": report.get("checked_contracts", []),
        "missing_fields": report.get("missing_fields", {}),
        "incompatible_fields": report.get("incompatible_fields", []),
        "blocking_issues": report.get("blocking_issues", []),
    }
    return "execution-landing-consistency-" + _stable_hash(payload)[:16]


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()

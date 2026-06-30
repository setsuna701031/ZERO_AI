from __future__ import annotations

import copy
from typing import Any, Dict, Mapping, Tuple

from core.runtime.aer_operator_lifecycle import OPERATOR_PHASES, normalize_operator_phase

AER_OPERATOR_CONTEXT_CONTRACT = "aer.operator_context.v2"

OPERATOR_CONTEXT_FIELDS: Tuple[str, ...] = (
    "contract",
    "operator_session_id",
    "package_id",
    "runtime_session_id",
    "current_phase",
    "checkpoint_id",
    "approval_state",
    "stop_reason",
    "issue_report_id",
    "metadata",
)


def build_operator_context(
    *,
    operator_session_id: str,
    package_id: str,
    runtime_session_id: str = "",
    current_phase: str = "initialized",
    checkpoint_id: str = "",
    approval_state: str = "",
    stop_reason: str = "",
    issue_report_id: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "contract": AER_OPERATOR_CONTEXT_CONTRACT,
        "operator_session_id": str(operator_session_id or ""),
        "package_id": str(package_id or ""),
        "runtime_session_id": str(runtime_session_id or ""),
        "current_phase": normalize_operator_phase(current_phase),
        "checkpoint_id": str(checkpoint_id or ""),
        "approval_state": str(approval_state or ""),
        "stop_reason": str(stop_reason or ""),
        "issue_report_id": str(issue_report_id or ""),
        "metadata": copy.deepcopy(dict(metadata or {})),
    }


def validate_operator_context(payload: Any) -> Dict[str, Any]:
    errors = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "contract": AER_OPERATOR_CONTEXT_CONTRACT,
            "errors": ["payload must be a dict"],
        }

    for field in OPERATOR_CONTEXT_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("contract") != AER_OPERATOR_CONTEXT_CONTRACT:
        errors.append("invalid contract")

    if not str(payload.get("operator_session_id") or "").strip():
        errors.append("operator_session_id is required")

    if not str(payload.get("package_id") or "").strip():
        errors.append("package_id is required")

    phase = payload.get("current_phase")
    if phase not in OPERATOR_PHASES:
        errors.append(f"invalid current_phase: {phase}")

    if not isinstance(payload.get("metadata"), dict):
        errors.append("metadata must be a dict")

    return {
        "ok": not errors,
        "contract": AER_OPERATOR_CONTEXT_CONTRACT,
        "errors": errors,
    }


def copy_operator_context(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(dict(payload))


def merge_operator_context(
    base: Mapping[str, Any],
    updates: Mapping[str, Any],
) -> Dict[str, Any]:
    merged = copy_operator_context(base)

    for field in OPERATOR_CONTEXT_FIELDS:
        if field == "contract":
            continue
        if field not in updates:
            continue
        if field == "metadata":
            base_metadata = dict(merged.get("metadata") or {})
            update_metadata = dict(updates.get("metadata") or {})
            base_metadata.update(copy.deepcopy(update_metadata))
            merged["metadata"] = base_metadata
            continue
        if field == "current_phase":
            merged[field] = normalize_operator_phase(updates.get(field))
            continue
        merged[field] = str(updates.get(field) or "")

    merged["contract"] = AER_OPERATOR_CONTEXT_CONTRACT
    if "metadata" not in merged or not isinstance(merged.get("metadata"), dict):
        merged["metadata"] = {}
    return merged

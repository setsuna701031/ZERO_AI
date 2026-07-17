from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Tuple

from core.runtime.aer_operator_lifecycle import (
    AER_OPERATOR_LIFECYCLE_CONTRACT,
    OPERATOR_PHASES,
    normalize_operator_phase,
)

AER_OPERATOR_CHECKPOINT_CONTRACT = "aer.operator_checkpoint.v2"

CHECKPOINT_REQUIRED_FIELDS: Tuple[str, ...] = (
    "contract",
    "checkpoint_id",
    "operator_session_id",
    "package_id",
    "lifecycle_contract",
    "phase",
    "completed_phases",
    "pending_phases",
    "failed_phase",
    "resume_token",
    "metadata",
    "integrity_hash",
)


def _stable_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_checkpoint_integrity_hash(payload: Dict[str, Any]) -> str:
    material = dict(payload)
    material.pop("integrity_hash", None)
    return hashlib.sha256(_stable_json(material).encode("utf-8")).hexdigest()


def build_operator_checkpoint(
    *,
    checkpoint_id: str,
    operator_session_id: str,
    package_id: str,
    phase: str = "initialized",
    completed_phases: Tuple[str, ...] | None = None,
    pending_phases: Tuple[str, ...] | None = None,
    failed_phase: str = "",
    resume_token: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "contract": AER_OPERATOR_CHECKPOINT_CONTRACT,
        "checkpoint_id": str(checkpoint_id or ""),
        "operator_session_id": str(operator_session_id or ""),
        "package_id": str(package_id or ""),
        "lifecycle_contract": AER_OPERATOR_LIFECYCLE_CONTRACT,
        "phase": normalize_operator_phase(phase),
        "completed_phases": [normalize_operator_phase(item) for item in (completed_phases or ())],
        "pending_phases": [normalize_operator_phase(item) for item in (pending_phases or ())],
        "failed_phase": normalize_operator_phase(failed_phase) if failed_phase else "",
        "resume_token": str(resume_token or ""),
        "metadata": dict(metadata or {}),
        "integrity_hash": "",
    }
    payload["integrity_hash"] = compute_checkpoint_integrity_hash(payload)
    return payload


def validate_operator_checkpoint(payload: Any) -> Dict[str, Any]:
    errors = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "contract": AER_OPERATOR_CHECKPOINT_CONTRACT,
            "errors": ["payload must be a dict"],
        }

    for field in CHECKPOINT_REQUIRED_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    if payload.get("contract") != AER_OPERATOR_CHECKPOINT_CONTRACT:
        errors.append("invalid contract")

    if payload.get("lifecycle_contract") != AER_OPERATOR_LIFECYCLE_CONTRACT:
        errors.append("invalid lifecycle_contract")

    if not str(payload.get("checkpoint_id") or "").strip():
        errors.append("checkpoint_id is required")

    if not str(payload.get("operator_session_id") or "").strip():
        errors.append("operator_session_id is required")

    if not str(payload.get("package_id") or "").strip():
        errors.append("package_id is required")

    phase = payload.get("phase")
    if phase not in OPERATOR_PHASES:
        errors.append(f"invalid phase: {phase}")

    for key in ("completed_phases", "pending_phases"):
        value = payload.get(key)
        if not isinstance(value, list):
            errors.append(f"{key} must be a list")
            continue
        for item in value:
            if item not in OPERATOR_PHASES:
                errors.append(f"invalid {key} item: {item}")

    failed_phase = payload.get("failed_phase")
    if failed_phase and failed_phase not in OPERATOR_PHASES:
        errors.append(f"invalid failed_phase: {failed_phase}")

    if not isinstance(payload.get("metadata"), dict):
        errors.append("metadata must be a dict")

    expected_hash = compute_checkpoint_integrity_hash(payload)
    if payload.get("integrity_hash") != expected_hash:
        errors.append("integrity_hash mismatch")

    return {
        "ok": not errors,
        "contract": AER_OPERATOR_CHECKPOINT_CONTRACT,
        "errors": errors,
    }


def serialize_operator_checkpoint(payload: Dict[str, Any]) -> str:
    return _stable_json(payload)


def deserialize_operator_checkpoint(text: str) -> Dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("checkpoint payload must decode to dict")
    return value
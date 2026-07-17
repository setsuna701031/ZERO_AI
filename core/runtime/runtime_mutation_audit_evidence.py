from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_evidence_surface import register_evidence


def export_runtime_mutation_audit_evidence(
    *,
    repo_root: Path | str,
    task_id: str,
    mutation_audit: Any,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Export and index an existing governed mutation audit payload.

    This helper only serializes and registers evidence. It does not create a
    mutation gateway, run mutation execution, schedule work, or alter runtime
    authority.
    """
    payload = _audit_payload(mutation_audit)
    if not payload:
        return {}

    root = Path(repo_root).resolve()
    safe_task_id = _safe_filename(task_id) or "runtime_mutation_task"
    evidence_dir = root / "workspace" / "evidence" / "mutation_audit"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{safe_task_id}_mutation_audit.json"

    evidence_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    surface_metadata = {
        "artifact_path": str(evidence_path),
        "evidence_path": str(evidence_path),
    }
    schema = _first_text(payload.get("schema"), payload.get("report_schema"))
    session_id = _first_text(payload.get("session_id"))
    audit_id = _first_text(payload.get("audit_id"), payload.get("id"))
    status = _first_text(payload.get("status"), payload.get("decision"))
    if schema:
        surface_metadata["schema"] = schema
    if session_id:
        surface_metadata["session_id"] = session_id
    if audit_id:
        surface_metadata["audit_id"] = audit_id
    if status:
        surface_metadata["status"] = status
    if isinstance(metadata, Mapping):
        surface_metadata.update(copy.deepcopy(dict(metadata)))

    register_evidence(
        task_id,
        "mutation_audit",
        evidence_path,
        surface_metadata,
        repo_root=root,
    )

    return {
        "evidence_type": "mutation_audit",
        "evidence_path": str(evidence_path),
        "artifact_path": str(evidence_path),
        "payload": copy.deepcopy(payload),
        "metadata": copy.deepcopy(surface_metadata),
    }


def _audit_payload(mutation_audit: Any) -> dict[str, Any]:
    if hasattr(mutation_audit, "to_dict") and callable(mutation_audit.to_dict):
        payload = mutation_audit.to_dict()
        return _json_safe(payload if isinstance(payload, dict) else {})
    if hasattr(mutation_audit, "payload"):
        payload = mutation_audit.payload
        return _json_safe(payload if isinstance(payload, dict) else {})
    return _json_safe(mutation_audit if isinstance(mutation_audit, dict) else {})


def _json_safe(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    decoded = json.loads(encoded)
    return decoded if isinstance(decoded, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("._-")[:120]


__all__ = ["export_runtime_mutation_audit_evidence"]

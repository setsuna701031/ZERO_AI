from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_evidence_surface import register_evidence


def export_runtime_recovery_evidence(
    *,
    repo_root: Path | str,
    task_id: str,
    recovery_report: Any,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Export and index an existing runtime recovery report.

    This helper is evidence-surface only. It serializes an already-produced
    recovery payload and registers the artifact without creating, executing, or
    scheduling recovery work.
    """
    payload = _recovery_payload(recovery_report)
    if not payload:
        return {}

    root = Path(repo_root).resolve()
    safe_task_id = _safe_filename(task_id) or "runtime_recovery_task"
    evidence_dir = root / "workspace" / "evidence" / "recovery"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{safe_task_id}_recovery_report.json"

    evidence_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    surface_metadata = {
        "artifact_path": str(evidence_path),
        "evidence_path": str(evidence_path),
    }
    schema = _first_text(payload.get("schema"), payload.get("report_schema"))
    recovery_id = _first_text(payload.get("recovery_id"), payload.get("id"))
    execution_id = _first_text(payload.get("execution_id"))
    status = _first_text(payload.get("status"), payload.get("recovery_status"))
    if schema:
        surface_metadata["schema"] = schema
    if recovery_id:
        surface_metadata["recovery_id"] = recovery_id
    if execution_id:
        surface_metadata["execution_id"] = execution_id
    if status:
        surface_metadata["status"] = status
    if isinstance(metadata, Mapping):
        surface_metadata.update(copy.deepcopy(dict(metadata)))

    register_evidence(
        task_id,
        "recovery_report",
        evidence_path,
        surface_metadata,
        repo_root=root,
    )

    return {
        "evidence_type": "recovery_report",
        "evidence_path": str(evidence_path),
        "artifact_path": str(evidence_path),
        "payload": copy.deepcopy(payload),
        "metadata": copy.deepcopy(surface_metadata),
    }


def _recovery_payload(recovery_report: Any) -> dict[str, Any]:
    if hasattr(recovery_report, "to_dict") and callable(recovery_report.to_dict):
        report = recovery_report.to_dict()
        return copy.deepcopy(report if isinstance(report, dict) else {})
    if hasattr(recovery_report, "payload"):
        report = recovery_report.payload
        return copy.deepcopy(report if isinstance(report, dict) else {})
    return copy.deepcopy(recovery_report if isinstance(recovery_report, dict) else {})


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


__all__ = ["export_runtime_recovery_evidence"]

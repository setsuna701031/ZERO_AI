from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from core.runtime.artifact_completion_report import (
    ARTIFACT_COMPLETION_REPORT_SCHEMA,
    ArtifactCompletionReport,
)
from core.runtime.runtime_evidence_surface import register_evidence


def export_task_intake_completion_evidence(
    *,
    repo_root: Path | str,
    task_id: str,
    completion_report: ArtifactCompletionReport | Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = (
        completion_report.to_dict()
        if isinstance(completion_report, ArtifactCompletionReport)
        else copy.deepcopy(dict(completion_report or {}))
    )
    if not payload:
        return {}

    payload.setdefault("schema", ARTIFACT_COMPLETION_REPORT_SCHEMA)
    payload.setdefault("evidence_type", "task_report")
    payload.setdefault("evidence_only", True)
    payload.setdefault("no_scheduler_execution", True)
    payload.setdefault("no_agent_loop_execution", True)

    root = Path(repo_root).resolve()
    safe_task_id = _safe_filename(task_id) or "task_intake"
    evidence_dir = root / "workspace" / "evidence" / "task_reports"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{safe_task_id}_completion_report.json"
    evidence_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    surface_metadata = {
        "artifact_path": str(evidence_path),
        "evidence_path": str(evidence_path),
        "schema": str(payload.get("schema") or ARTIFACT_COMPLETION_REPORT_SCHEMA),
        "status": str(payload.get("status") or ""),
        "fingerprint": str(payload.get("fingerprint") or ""),
        "artifact_count": len(payload.get("artifacts") or []),
    }
    if isinstance(metadata, Mapping):
        surface_metadata.update(copy.deepcopy(dict(metadata)))

    register_evidence(
        task_id,
        "task_report",
        evidence_path,
        surface_metadata,
        repo_root=root,
    )

    return {
        "evidence_type": "task_report",
        "evidence_path": str(evidence_path),
        "artifact_path": str(evidence_path),
        "schema": surface_metadata["schema"],
        "payload": copy.deepcopy(payload),
        "metadata": copy.deepcopy(surface_metadata),
    }


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("._-")[:120]


__all__ = ["export_task_intake_completion_evidence"]

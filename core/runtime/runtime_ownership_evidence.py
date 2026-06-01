from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_evidence_surface import register_evidence


RUNTIME_OWNERSHIP_EVIDENCE_SCHEMA = "runtime_ownership_evidence.v1"


def export_runtime_ownership_evidence(
    *,
    repo_root: Path | str,
    task_id: str,
    ownership_report: Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Export an ownership scan/policy report to the shared evidence surface."""
    payload = copy.deepcopy(dict(ownership_report or {}))
    if not payload:
        return {}
    payload.setdefault("schema", RUNTIME_OWNERSHIP_EVIDENCE_SCHEMA)
    payload.setdefault("evidence_type", "runtime_ownership")
    payload.setdefault("evidence_only", True)
    payload.setdefault("no_execution_added", True)

    root = Path(repo_root).resolve()
    safe_task_id = _safe_filename(task_id) or "runtime_ownership_task"
    evidence_dir = root / "workspace" / "evidence" / "runtime_ownership"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{safe_task_id}_runtime_ownership.json"

    evidence_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    surface_metadata = {
        "artifact_path": str(evidence_path),
        "evidence_path": str(evidence_path),
        "schema": str(payload.get("schema") or RUNTIME_OWNERSHIP_EVIDENCE_SCHEMA),
        "ok": bool(payload.get("ok", False)),
        "violation_count": int(
            payload.get("violation_count")
            or payload.get("policy", {}).get("violation_count")
            or 0
        ),
    }
    if isinstance(metadata, Mapping):
        surface_metadata.update(copy.deepcopy(dict(metadata)))

    register_evidence(
        task_id,
        "runtime_ownership",
        evidence_path,
        surface_metadata,
        repo_root=root,
    )

    return {
        "evidence_type": "runtime_ownership",
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


__all__ = [
    "RUNTIME_OWNERSHIP_EVIDENCE_SCHEMA",
    "export_runtime_ownership_evidence",
]

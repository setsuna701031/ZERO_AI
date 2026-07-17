from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_evidence_surface import register_evidence


RUNTIME_EXECUTION_AUTHORITY_EVIDENCE_SCHEMA = "runtime_execution_authority_evidence.v1"


def build_execution_authority_evidence(
    decision: Any,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = decision.to_dict() if hasattr(decision, "to_dict") else {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "schema": RUNTIME_EXECUTION_AUTHORITY_EVIDENCE_SCHEMA,
        "evidence_type": "runtime_execution_authority",
        "allowed": bool(payload.get("allowed")),
        "blocked": bool(payload.get("blocked")),
        "decision_id": str(payload.get("decision_id") or ""),
        "source": str(payload.get("source") or ""),
        "action_type": str(payload.get("action_type") or ""),
        "reason": str(payload.get("reason") or ""),
        "canonical_path": list(payload.get("canonical_path") or []),
        "decision": copy.deepcopy(payload),
        "metadata": copy.deepcopy(dict(metadata or {})),
        "no_execution_performed": True,
        "evidence_only": True,
    }


def export_execution_authority_evidence(
    *,
    repo_root: Path | str,
    task_id: str,
    decision: Any,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_execution_authority_evidence(decision, metadata=metadata)
    root = Path(repo_root).resolve()
    safe_task_id = _safe_filename(task_id) or "runtime_execution_authority_task"
    evidence_dir = root / "workspace" / "evidence" / "execution_authority"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{safe_task_id}_execution_authority.json"

    evidence_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    surface_metadata = {
        "artifact_path": str(evidence_path),
        "evidence_path": str(evidence_path),
        "schema": RUNTIME_EXECUTION_AUTHORITY_EVIDENCE_SCHEMA,
        "decision_id": payload["decision_id"],
        "allowed": payload["allowed"],
        "blocked": payload["blocked"],
        "reason": payload["reason"],
    }
    if isinstance(metadata, Mapping):
        surface_metadata.update(copy.deepcopy(dict(metadata)))

    register_evidence(
        task_id,
        "runtime_execution_authority",
        evidence_path,
        surface_metadata,
        repo_root=root,
    )

    return {
        "evidence_type": "runtime_execution_authority",
        "evidence_path": str(evidence_path),
        "artifact_path": str(evidence_path),
        "schema": RUNTIME_EXECUTION_AUTHORITY_EVIDENCE_SCHEMA,
        "payload": copy.deepcopy(payload),
        "metadata": copy.deepcopy(surface_metadata),
    }


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("._-")[:120]


__all__ = [
    "RUNTIME_EXECUTION_AUTHORITY_EVIDENCE_SCHEMA",
    "build_execution_authority_evidence",
    "export_execution_authority_evidence",
]

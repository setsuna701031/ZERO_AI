from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_contract_seal import (
    RUNTIME_CONTRACT_SEAL_SCHEMA,
    RuntimeContractSealReport,
)
from core.runtime.runtime_evidence_surface import register_evidence


def export_runtime_contract_seal_evidence(
    *,
    repo_root: Path | str,
    task_id: str,
    seal_report: RuntimeContractSealReport | Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = (
        seal_report.to_dict()
        if isinstance(seal_report, RuntimeContractSealReport)
        else copy.deepcopy(dict(seal_report or {}))
    )
    if not payload:
        return {}
    payload.setdefault("schema", RUNTIME_CONTRACT_SEAL_SCHEMA)
    payload.setdefault("evidence_type", "runtime_contract_seal")
    payload.setdefault("evidence_only", True)
    payload.setdefault("no_execution_performed", True)

    root = Path(repo_root).resolve()
    safe_task_id = _safe_filename(task_id) or "runtime_contract_task"
    evidence_dir = root / "workspace" / "evidence" / "runtime_contract"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{safe_task_id}_runtime_contract_seal.json"

    evidence_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    surface_metadata = {
        "artifact_path": str(evidence_path),
        "evidence_path": str(evidence_path),
        "schema": str(payload.get("schema") or RUNTIME_CONTRACT_SEAL_SCHEMA),
        "sealed": bool(payload.get("sealed")),
        "status": str(payload.get("status") or ""),
        "fingerprint": str(payload.get("fingerprint") or ""),
    }
    if isinstance(metadata, Mapping):
        surface_metadata.update(copy.deepcopy(dict(metadata)))

    register_evidence(
        task_id,
        "runtime_contract_seal",
        evidence_path,
        surface_metadata,
        repo_root=root,
    )

    return {
        "evidence_type": "runtime_contract_seal",
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


__all__ = ["export_runtime_contract_seal_evidence"]

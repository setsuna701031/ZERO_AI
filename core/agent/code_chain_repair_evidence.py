from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from core.agent.code_chain_repair_report import build_code_chain_repair_export_payload
from core.runtime.runtime_evidence_surface import register_evidence


def export_code_chain_repair_evidence(
    *,
    repo_root: Path,
    task_id: str,
    repair_result_report: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(repair_result_report, dict) or not repair_result_report:
        return {}

    root = Path(repo_root).resolve()
    safe_task_id = _safe_filename(task_id) or "code_chain_task"
    evidence_dir = root / "workspace" / "evidence" / "code_chain_repair"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{safe_task_id}_repair_result_report.json"

    payload = build_code_chain_repair_export_payload(repair_result_report)
    metadata = {
        "evidence_type": "code_chain_repair_result_report",
        "evidence_path": str(evidence_path),
        "artifact_path": str(evidence_path),
        "schema": payload["schema"],
    }
    payload["evidence_path"] = metadata["evidence_path"]
    payload["artifact_path"] = metadata["artifact_path"]

    evidence_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    register_evidence(
        task_id,
        metadata["evidence_type"],
        evidence_path,
        {
            "artifact_path": metadata["artifact_path"],
            "evidence_path": metadata["evidence_path"],
            "schema": metadata["schema"],
        },
        repo_root=root,
    )

    return {
        **metadata,
        "payload": copy.deepcopy(payload),
    }


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("._-")[:120]

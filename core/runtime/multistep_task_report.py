from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.runtime.runtime_evidence_surface import register_evidence


MULTISTEP_TASK_REPORT_SCHEMA = "multistep_engineering_task_report.v1"


@dataclass(frozen=True)
class MultiStepTaskReport:
    task_id: str
    status: str
    lifecycle: tuple[dict[str, Any], ...]
    plan: dict[str, Any]
    execution_result: dict[str, Any]
    artifacts: tuple[dict[str, Any], ...]
    schema: str = MULTISTEP_TASK_REPORT_SCHEMA
    fingerprint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", _fingerprint(self._payload(include_fingerprint=False)))

    def to_dict(self) -> dict[str, Any]:
        return self._payload(include_fingerprint=True)

    def _payload(self, *, include_fingerprint: bool) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "task_id": self.task_id,
            "status": self.status,
            "lifecycle": copy.deepcopy(list(self.lifecycle)),
            "plan": copy.deepcopy(self.plan),
            "execution_result": copy.deepcopy(self.execution_result),
            "artifacts": copy.deepcopy(list(self.artifacts)),
            "metadata": copy.deepcopy(self.metadata),
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
        return payload


def build_multistep_task_report(
    *,
    task_id: str,
    status: str,
    lifecycle: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    plan: Mapping[str, Any],
    execution_result: Mapping[str, Any],
    artifacts: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    metadata: Mapping[str, Any] | None = None,
) -> MultiStepTaskReport:
    return MultiStepTaskReport(
        task_id=str(task_id or ""),
        status=str(status or ""),
        lifecycle=tuple(copy.deepcopy(dict(item)) for item in lifecycle if isinstance(item, Mapping)),
        plan=copy.deepcopy(dict(plan or {})),
        execution_result=copy.deepcopy(dict(execution_result or {})),
        artifacts=tuple(copy.deepcopy(dict(item)) for item in artifacts if isinstance(item, Mapping)),
        metadata={
            **copy.deepcopy(dict(metadata or {})),
            "report_only": True,
            "no_runtime_core_capability_added": True,
        },
    )


def export_multistep_task_report_evidence(
    *,
    repo_root: Path | str,
    task_id: str,
    report: MultiStepTaskReport | Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = report.to_dict() if isinstance(report, MultiStepTaskReport) else copy.deepcopy(dict(report or {}))
    if not payload:
        return {}

    payload.setdefault("schema", MULTISTEP_TASK_REPORT_SCHEMA)
    payload.setdefault("evidence_type", "task_report")
    payload.setdefault("evidence_only", True)

    root = Path(repo_root).resolve()
    safe_task_id = _safe_filename(task_id) or "multistep_task"
    evidence_dir = root / "workspace" / "evidence" / "multistep_task"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / f"{safe_task_id}_multistep_task_report.json"
    evidence_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )

    surface_metadata = {
        "artifact_path": str(evidence_path),
        "evidence_path": str(evidence_path),
        "schema": str(payload.get("schema") or MULTISTEP_TASK_REPORT_SCHEMA),
        "report_type": "multistep_engineering_task_report",
        "status": str(payload.get("status") or ""),
        "step_count": int((payload.get("execution_result") or {}).get("step_count") or 0),
        "artifact_count": len(payload.get("artifacts") or []),
        "fingerprint": str(payload.get("fingerprint") or ""),
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


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "MULTISTEP_TASK_REPORT_SCHEMA",
    "MultiStepTaskReport",
    "build_multistep_task_report",
    "export_multistep_task_report_evidence",
]

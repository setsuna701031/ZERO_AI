from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_state_hygiene import clone_runtime_export, make_json_safe


class RuntimeAuditRegistry:
    def __init__(self) -> None:
        self._artifacts: Dict[str, Dict[str, Any]] = {}
        self._counter = 0

    def register_runtime_audit_artifact(self, artifact: Any) -> Dict[str, Any]:
        safe_artifact = clone_runtime_export(artifact) if isinstance(artifact, Mapping) else {}
        artifact_id = _first_nonempty(safe_artifact.get("artifact_id"), safe_artifact.get("id"))
        if not artifact_id:
            artifact_id = self._fallback_artifact_id(safe_artifact)
        safe_artifact["artifact_id"] = artifact_id
        self._artifacts[artifact_id] = clone_runtime_export(safe_artifact)
        return clone_runtime_export(safe_artifact)

    def get_runtime_audit_artifact(self, artifact_id: Any) -> Optional[Dict[str, Any]]:
        normalized_id = str(artifact_id or "").strip()
        if not normalized_id:
            return None
        artifact = self._artifacts.get(normalized_id)
        if artifact is None:
            return None
        return clone_runtime_export(artifact)

    def list_runtime_audit_artifacts(self, task_id: Any = None, status: Any = None) -> List[Dict[str, Any]]:
        task_filter = str(task_id or "").strip()
        status_filter = str(status or "").strip()

        results: List[Dict[str, Any]] = []
        for artifact_id in sorted(self._artifacts.keys()):
            artifact = self._artifacts[artifact_id]
            if task_filter and str(artifact.get("task_id") or "").strip() != task_filter:
                continue
            if status_filter and str(artifact.get("status") or "").strip() != status_filter:
                continue
            results.append(clone_runtime_export(artifact))
        return results

    def clear(self) -> None:
        self._artifacts.clear()
        self._counter = 0

    def _fallback_artifact_id(self, artifact: Mapping[str, Any]) -> str:
        self._counter += 1
        task_id = _first_nonempty(artifact.get("task_id"), "unknown_task")
        status = _first_nonempty(artifact.get("status"), "unknown")
        payload = {
            "task_id": artifact.get("task_id"),
            "status": artifact.get("status"),
            "summary": artifact.get("summary"),
            "counter": self._counter,
        }
        digest = hashlib.sha1(
            json.dumps(make_json_safe(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        return f"runtime_audit:{task_id}:{status}:{digest}"


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""

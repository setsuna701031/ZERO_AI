from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping

from core.tasks.runtime_state_hygiene import freeze_runtime_export, make_json_safe
from core.tasks.runtime_replay_narrative import build_runtime_replay_narrative


RUNTIME_AUDIT_ARTIFACT_TYPE = "runtime_audit_artifact"
RUNTIME_AUDIT_ARTIFACT_VERSION = "runtime_audit_artifact.v1"


def build_runtime_audit_artifact(snapshot: Any, narrative: Any = None) -> Dict[str, Any]:
    safe_snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    resolved_narrative = narrative if narrative is not None else build_runtime_replay_narrative(snapshot)
    safe_narrative = resolved_narrative if isinstance(resolved_narrative, Mapping) else build_runtime_replay_narrative(snapshot)

    artifact = {
        "artifact_type": RUNTIME_AUDIT_ARTIFACT_TYPE,
        "artifact_version": RUNTIME_AUDIT_ARTIFACT_VERSION,
        "artifact_id": "",
        "task_id": _first_nonempty(safe_snapshot.get("task_id"), safe_narrative.get("task_id")),
        "status": _first_nonempty(safe_snapshot.get("status"), safe_narrative.get("status"), "unknown"),
        "goal": _first_nonempty(safe_snapshot.get("goal")),
        "summary": _first_nonempty(safe_snapshot.get("replay_summary"), safe_narrative.get("summary")),
        "timeline_summary": _mapping_or_empty(safe_snapshot.get("timeline_summary")),
        "narrative_summary": _first_nonempty(safe_narrative.get("summary")),
        "failure_summary": _first_nonempty(safe_narrative.get("failure_narrative")),
        "blocker_summary": _first_nonempty(safe_narrative.get("blocker_narrative")),
        "next_observation": _first_nonempty(safe_narrative.get("next_observation")),
        "kernel_status": _mapping_or_empty(safe_snapshot.get("kernel_status")),
        "normalized_events": _list_or_empty(safe_snapshot.get("normalized_events")),
        "timeline": _list_or_empty(safe_snapshot.get("timeline")),
        "blockers": _list_or_empty(safe_snapshot.get("blockers")),
        "failed_events": _list_or_empty(safe_snapshot.get("failed_events")),
        "raw_snapshot": freeze_runtime_export(snapshot),
        "raw_narrative": freeze_runtime_export(resolved_narrative),
    }
    artifact["artifact_id"] = _build_artifact_id(artifact)
    return freeze_runtime_export(artifact)


def _mapping_or_empty(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _list_or_empty(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _build_artifact_id(artifact: Mapping[str, Any]) -> str:
    task_id = _first_nonempty(artifact.get("task_id"), "unknown_task")
    status = _first_nonempty(artifact.get("status"), "unknown")
    payload = {
        "task_id": artifact.get("task_id"),
        "status": artifact.get("status"),
        "goal": artifact.get("goal"),
        "summary": artifact.get("summary"),
        "timeline_summary": artifact.get("timeline_summary"),
        "blockers": artifact.get("blockers"),
        "failed_events": artifact.get("failed_events"),
    }
    encoded = json.dumps(make_json_safe(payload), ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]
    return f"runtime_audit:{task_id}:{status}:{digest}"

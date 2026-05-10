from __future__ import annotations

from typing import Any, Dict, Mapping

from core.tasks.runtime_replay_narrative import build_runtime_replay_narrative


def format_runtime_replay_summary(snapshot_or_narrative: Any) -> str:
    narrative = _ensure_narrative(snapshot_or_narrative)
    return "\n".join(
        [
            "Runtime Replay Summary:",
            f"- task_id: {_display(narrative.get('task_id'))}",
            f"- status: {_display(narrative.get('status'))}",
            f"- summary: {_display(narrative.get('summary'))}",
            f"- failure: {_display(narrative.get('failure_narrative'))}",
            f"- blocker: {_display(narrative.get('blocker_narrative'))}",
            f"- next_observation: {_display(narrative.get('next_observation'))}",
        ]
    )


def format_runtime_replay_detail(snapshot_or_narrative: Any) -> str:
    narrative = _ensure_narrative(snapshot_or_narrative)
    return "\n".join(
        [
            "Runtime Replay Detail:",
            f"- task_id: {_display(narrative.get('task_id'))}",
            f"- status: {_display(narrative.get('status'))}",
            f"- title: {_display(narrative.get('title'))}",
            f"- summary: {_display(narrative.get('summary'))}",
            f"- timeline: {_display(narrative.get('timeline_narrative'))}",
            f"- failure: {_display(narrative.get('failure_narrative'))}",
            f"- blocker: {_display(narrative.get('blocker_narrative'))}",
            f"- next_observation: {_display(narrative.get('next_observation'))}",
        ]
    )


def _ensure_narrative(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping) and _looks_like_narrative(value):
        return {
            "task_id": _safe_str(value.get("task_id")),
            "status": _safe_str(value.get("status")) or "unknown",
            "title": _safe_str(value.get("title")) or "task",
            "summary": _safe_str(value.get("summary")) or "task is unknown with 0 replay event(s).",
            "timeline_narrative": _safe_str(value.get("timeline_narrative")) or "No replay timeline events are available.",
            "failure_narrative": _safe_str(value.get("failure_narrative")) or "No failed replay events were captured.",
            "blocker_narrative": _safe_str(value.get("blocker_narrative")) or "No blockers were captured.",
            "next_observation": _safe_str(value.get("next_observation")) or "Inspect the replay snapshot fields before deciding the next human action.",
            "raw_snapshot": value.get("raw_snapshot"),
        }
    return build_runtime_replay_narrative(value)


def _looks_like_narrative(value: Mapping[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "timeline_narrative",
            "failure_narrative",
            "blocker_narrative",
            "next_observation",
        )
    )


def _display(value: Any) -> str:
    text = _safe_str(value)
    return text if text else "<none>"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
